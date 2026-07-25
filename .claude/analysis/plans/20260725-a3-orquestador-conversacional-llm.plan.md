# Plan — A3: Orquestador conversacional LLM · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-25 · **Tipo**: plan de implementación por fases.
> **Base**: [20260724-a1-cliente-gemini-function-calling.plan.md](.claude/analysis/plans/20260724-a1-cliente-gemini-function-calling.plan.md)
> (ejecutado — `gemini_client.py` con tools y tool calls parseadas) y
> [20260724-a2-contrato-herramientas-agente.plan.md](.claude/analysis/plans/20260724-a2-contrato-herramientas-agente.plan.md)
> (ejecutado — las 5 tools + `ToolContext` + `execute_tool`, smoke live 2/2).
> Insumo externo: tarea **A3** del brain y sus relaciones (`Enunciado del reto` — lo
> que NO quieren ver; `Stack y arquitectura` — orquestador+tools; `Guiones de Demo
> Conversacional (MVP)` — tono y arco objetivo).
> **Proyectos afectados**: backend. (El frontend consumirá el endpoint nuevo en la
> Feature D — otro plan.)
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

Que la conversación deje de ser el formulario por regex de
[channel_handler.py](backend/app/services/channel_handler.py) y pase a ser un
**agente**: Gemini conversa con tono cálido colombiano, decide qué preguntar, y llama
a las 5 tools de A2. **El LLM decide qué preguntar y cómo explicar; los motores
deciden qué recomendar y a qué precio.** Elimina lo que el reto explícitamente NO
quiere ver: "experiencias frías que parezcan un formulario estándar (ni un formulario
disfrazado de chatbot)".

Entra por un endpoint nuevo `POST /api/v1/conversations/{id}/message` (texto libre).
Los endpoints estructurados actuales **se conservan** (panel/tests). El
`ChannelHandler` regex **no se borra** (plan B del domingo; los webhooks siguen con él
hasta otra tarea).

## Contexto / hallazgos del análisis

**Piezas ya verdes que este plan ensambla** (línea base: **174 passed + 5 skipped**):

- [gemini_client.py](backend/app/services/integrations/gemini_client.py) (A1):
  `generate_reply(contents, tools=, system_instruction=)` → `GeminiReply`
  (text | tool_call | error con fallback en español). **Falta una pieza para el loop**:
  helpers para construir el historial de tool-use que la API exige — el mensaje
  `model` con la part `functionCall` y el mensaje con la part `functionResponse`
  (`{"functionResponse": {"name", "response"}}`). Hoy el módulo solo arma parts de
  texto/audio → la Fase 1 agrega esos 2 builders (aditivo, mismo estilo).
- [agent_tools.py](backend/app/services/agent_tools.py) (A2): `tool_declarations()`
  (Gemini las aceptó en vivo, 2/2) y `execute_tool(name, args, ctx)` con errores
  controlados — el LLM puede alucinar nombres/saltarse pasos y recibe un error que le
  permite corregir. `ToolContext` = estado del funnel que posee el código.
- [conversation.py](backend/app/services/conversation.py): `conversation_service`
  (instancia compartida entre canales) con `create/get` y el repo en memoria;
  [ConversationResponse](backend/app/schemas/conversation.py#L62-L70) tiene
  `messages`, `profile`, `recommendation`, `quote`, `application`, `state`,
  `next_action` — la sesión ya puede persistir todo lo que el orquestador produce.
- [conversations.py](backend/app/api/routes/conversations.py): router delgado; el
  endpoint nuevo sigue su patrón exacto (404 vía HTTPException, response_model).
- [test_e2e_happy_path.py](backend/tests/test_e2e_happy_path.py): usa los endpoints
  estructurados, que **no cambian** → sigue verde sin tocarlo. El criterio de A3 "el
  e2e se adapta y pasa" se cumple así: el e2e viejo pasa intacto + se agrega el e2e
  nuevo de conversación libre (Fase 4).

**Del vault (tono y reglas del system prompt):** los Guiones de Demo marcan el arco:
saludo con nombre si es afiliado, respuesta empática a objeciones ("Tienes toda la
razón..."), máximo 1-2 preguntas por turno, cierre con confirmación explícita. El
Enunciado y el brain fijan las reglas duras: precios/coberturas SOLO de las tools
(jamás inventados), lógica explicable (las razones vienen del motor), consentimiento
explícito antes de cerrar.

**Decisiones de diseño resueltas en el análisis:**

1. **Loop del orquestador** (`app/services/orchestrator.py`, service que compone
   services — patrón permitido):
   ```
   respond(session_id, texto) →
     sesión = conversation_service.get(id)          (None → el router da 404)
     ctx = ToolContext desde la sesión               (profile/quote/recommendation)
     contents = historial de sesión.messages         (user→user, assistant→model)
     hasta MAX_TOOL_ROUNDS (5):
       reply = generate_reply(contents, tools=tool_declarations(), system_instruction=PROMPT+estado)
       si reply es tool_call → resultado = execute_tool(...) →
         contents += [model(functionCall), user(functionResponse)] y repite
       si reply es text → romper
       si reply es error → texto = FALLBACK_MESSAGE y romper
     sincronizar ctx → sesión (profile/quote/recommendation/application + state)
     append user+assistant a sesión.messages, persistir, devolver sesión
   ```
2. **Historial entre turnos**: `session.messages` guarda solo la transcripción
   user/assistant (los intercambios de tool-use son transitorios del turno). Para que
   el LLM no pierda el estado del funnel entre turnos, el system prompt de cada turno
   incluye un **resumen de estado generado por código** (perfil capturado sí/no,
   producto recomendado, prima vigente del ctx — valores del motor, no del LLM).
3. **Sincronización ctx ↔ sesión**: mismo mapeo que ya usan
   [conversation.py:50-57](backend/app/services/conversation.py#L50-L57) y
   `cerrar_venta` (A2): `ctx.profile`→`session.profile` directo;
   `ctx.quote` dict → `QuoteDetail` (subset de claves); `ctx.recommendation` dict →
   `Recommendation` (product_id/product_name/reasons). Estados: hay quote →
   `quote_ready`; cerró venta → `ready_for_payment` (+ `session.application`).
4. **Body del endpoint**: `{"content": "texto"}` (schema nuevo `MessageRequest`,
   `min_length=1` → 422 automático de FastAPI si va vacío). Respuesta:
   `ConversationResponse` completo (el front pintará `messages` + `state`).
5. **Gemini caído** → el turno responde 200 con el mensaje de disculpa como respuesta
   del asistente (nunca 500 — criterio heredado de A1). Cero red en tests: el LLM se
   mockea con respuestas guionadas (`monkeypatch` de `generate_reply` en el módulo
   orchestrator).

## Decisiones pendientes (bloqueantes)

(ninguna — las 5 de diseño quedaron resueltas arriba.)

## Principios

- Verde por fase (línea base: 174 passed + 5 skipped); el e2e estructurado existente
  no se toca y debe seguir verde en TODAS las fases.
- **Aditivo puro**: ni `channel_handler.py`, ni los endpoints actuales, ni los motores
  ni las tools de A2 se modifican. `gemini_client` solo gana 2 helpers.
- Tests sin red (LLM guionado con monkeypatch); lo live es una fase opcional gated.
- El precio que el bot cita = el del motor, verificado centavo a centavo en el e2e
  (criterio de A3).
- Config por env vars existentes; cero dependencias nuevas; contrato HTTP explícito.

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | backend | Ninguno | 5m | _(sin commit)_ |
| 1 | Helpers de historial tool-use en `gemini_client` | backend | Aditivo | 15m | `feat(back): add function call history parts to gemini client` |
| 2 | `orchestrator.py`: loop LLM + tools + sesión | backend | Aditivo | 40m | `feat(back): add llm conversation orchestrator` |
| 3 | Endpoint `POST /{id}/message` | backend | Aditivo | 20m | `feat(back): add free text message endpoint to conversations` |
| 4 | E2E de conversación libre (LLM guionado) | backend | Aditivo | 25m | `test(back): add orchestrated conversation e2e with scripted llm` |
| 5 | _(opcional)_ Conversación live real (gated) | backend | Aditivo | 15m | `test(back): add gated live check for orchestrator flow` |

Total: ~2h (1h45m sin la Fase 5). Recortable: solo la Fase 5 (el resto es el corazón
de A3; recortar la 4 dejaría sin verificar el criterio central del precio).

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: backend
**Objetivo**: confirmar punto de partida verde.
**Archivos afectados**: ninguno.
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` → **174 passed + 5 skipped**.
2. Confirmar que no existen `app/services/orchestrator.py` ni tests homónimos.
3. Confirmar `GEMINI_API_KEY` en `.env` (solo para la Fase 5 opcional).

**Pruebas / verificación**: las de arriba.
**Riesgos**: ninguno.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit)_

---

## Fase 1 — Helpers de historial tool-use en `gemini_client`

**Proyecto**: backend
**Objetivo**: los 2 builders que le faltan al cliente A1 para armar el loop de
function calling multi-vuelta.
**Archivos afectados**:
- [gemini_client.py](backend/app/services/integrations/gemini_client.py) — agregar,
  junto a `text_part`/`audio_part`:
  - `function_call_part(name: str, args: dict) -> dict` →
    `{"functionCall": {"name": name, "args": args}}` (reconstruye la part del turno
    `model` a partir del `GeminiReply` parseado).
  - `function_response_part(name: str, response: dict) -> dict` →
    `{"functionResponse": {"name": name, "response": response}}`.
- [test_gemini_client.py](backend/tests/test_gemini_client.py) — ampliar (TDD).

**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Tests primero: shape exacto de ambas parts; un flujo de 2 vueltas simulado — la
   secuencia `[user(text), model(functionCall), user(functionResponse)]` viaja intacta
   en el payload de `generate_reply` (mock httpx capturando el JSON).
2. Implementar los 2 helpers (puros, sin lógica).

**Pruebas / verificación**: pytest verde (174+nuevos + 5 skipped).
**Riesgos**: ninguno.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `feat(back): add function call history parts to gemini client`

---

## Fase 2 — `orchestrator.py`: loop LLM + tools + sesión

**Proyecto**: backend
**Objetivo**: el corazón de A3 — el service que ejecuta el loop del diseño (Contexto,
decisión 1) con el LLM mockeado en tests.
**Archivos afectados**:
- `backend/app/services/orchestrator.py` — **nuevo**:
  - `SYSTEM_PROMPT` (constante, español): identidad (asistente de seguros de
    Colsubsidio), tono colombiano cercano según los Guiones de Demo, reglas duras:
    precios y coberturas SOLO de las tools (jamás inventar), máx. 1-2 preguntas por
    turno, explicar con las razones del motor, pedir consentimiento explícito antes de
    `cerrar_venta`.
  - `MAX_TOOL_ROUNDS = 5`.
  - `respond(session_id: str, content: str) -> ConversationResponse | None` (None si
    la sesión no existe — el router lo convierte en 404): implementa el loop completo
    con sincronización ctx↔sesión y resumen de estado inyectado al system prompt
    (decisiones 1-3 del Contexto).
- `backend/tests/test_orchestrator.py` — **nuevo**: LLM guionado con `monkeypatch` de
  `orchestrator.generate_reply` (lista de `GeminiReply` a devolver en orden).

**Impacto en contrato API (front↔back)**: No (service interno; el endpoint llega en
Fase 3).
**Acciones**:
1. Tests primero (guionados, sin red):
   - respuesta directa de texto → mensaje user + assistant quedan en la sesión,
     estado intacto.
   - tool_call `perfilar_cliente` → texto: la tool se ejecutó (ctx→sesión con perfil),
     el `functionResponse` viajó en los `contents` de la 2ª llamada, la respuesta
     final es el texto.
   - cadena perfilar → cotizar → texto: `session.quote.monthly_premium` == el del
     motor (`QuoteService`) exacto; estado `quote_ready`.
   - tool_call con nombre alucinado → el error controlado de `execute_tool` viaja como
     functionResponse y el LLM puede responder texto (no explota).
   - `GeminiReply(kind="error")` → la respuesta del asistente es el fallback, sin
     excepción.
   - más de `MAX_TOOL_ROUNDS` tool_calls seguidas → corta con fallback (sin loop
     infinito).
   - sesión inexistente → `respond` devuelve None.
2. Implementar el service.

**Pruebas / verificación**: pytest verde; el e2e estructurado viejo sigue verde.
**Riesgos**: el mapeo ctx→sesión pierde `annual_premium` (QuoteDetail no lo tiene) —
irrelevante para el MVP (el bot cita mensual); anotado para C3/persistencia.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 3 sin aprobación del usuario.
**Commit sugerido**: `feat(back): add llm conversation orchestrator`

---

## Fase 3 — Endpoint `POST /api/v1/conversations/{id}/message`

**Proyecto**: backend
**Objetivo**: la puerta HTTP del agente (texto libre).
**Archivos afectados**:
- [schemas/conversation.py](backend/app/schemas/conversation.py) — `MessageRequest
  {content: str}` con `min_length=1`.
- [api/routes/conversations.py](backend/app/api/routes/conversations.py) — endpoint
  `POST /{session_id}/message` → `orchestrator.respond(...)`; None → 404;
  respuesta `ConversationResponse` (200).
- `backend/tests/test_conversations_router.py` o archivo nuevo — ampliar.

**Impacto en contrato API (front↔back)**: **Sí — aditivo.** Ruta nueva
`POST /api/v1/conversations/{session_id}/message`, body `{"content": str}`, respuesta
`ConversationResponse` (mismo shape que ya devuelven los demás endpoints), 404 sesión
inexistente, 422 body inválido. Los endpoints existentes NO cambian. **Quién actualiza
el otro lado**: la Feature D (chat web) en su propio plan — hoy el front no consume
nada de esto.
**Acciones**:
1. Tests primero (LLM guionado): 200 con la respuesta del asistente en `messages`;
   404 sesión inexistente; 422 content vacío/ausente (nunca 500); Gemini caído
   (mock error) → 200 con fallback como texto del asistente.
2. Implementar schema + endpoint (router delgado, patrón existente).

**Pruebas / verificación**: pytest verde; manual: levantar uvicorn y
`curl -X POST .../conversations` + `curl -X POST .../conversations/{id}/message -d '{"content": "hola"}'`
(con `GEMINI_API_KEY` real responde el agente de verdad).
**Riesgos**: ninguno nuevo (el loop ya está probado; esto es la puerta).

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 4 sin aprobación del usuario.
**Commit sugerido**: `feat(back): add free text message endpoint to conversations`

---

## Fase 4 — E2E de conversación libre (LLM guionado)

**Proyecto**: backend
**Objetivo**: los criterios de aceptación de A3 de punta a punta, sin red.
**Archivos afectados**:
- `backend/tests/test_e2e_orchestrator.py` — **nuevo** (el
  [e2e estructurado](backend/tests/test_e2e_happy_path.py) queda intacto y verde):
  - **Prospecto** (sin documento): "quiero proteger a mi familia" → guion de
    GeminiReply que perfila con declarados → recomienda → cotiza → responde texto
    citando la prima → **assert: la prima del texto/sesión == `QuoteService`
    directo, centavo a centavo** (criterio central).
  - **Afiliado** (con SERIE de un CSV de prueba): mismo arco vía
    `perfilar_cliente(document_number=...)` → `afiliado: True` y perfil de la base.
  - Conversación completa hasta `cerrar_venta` con consentimiento → estado final
    `ready_for_payment` vía `GET /{id}`.
  - Sin formato rígido: los mensajes user del guion son texto libre coloquial.

**Impacto en contrato API (front↔back)**: No (solo tests).
**Acciones**: 1. Escribir el e2e guionado. 2. Suite completa verde.
**Pruebas / verificación**: pytest verde (los 174 previos + fases 1-3 + este e2e).
**Riesgos**: guiones frágiles si asertan textos exactos del LLM → assertar datos del
motor y estados, no prosa.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 5 sin aprobación del usuario.
**Commit sugerido**: `test(back): add orchestrated conversation e2e with scripted llm`

---

## Fase 5 — _(opcional)_ Conversación live real (gated)

**Proyecto**: backend
**Objetivo**: una conversación corta real contra Gemini (2-3 turnos) para validar que
el system prompt + tools producen el arco esperado — el equivalente A3 de los smokes
live de A1/A2 (que son los que han cazado los problemas reales). Gasta ~4-6 llamadas.
**Archivos afectados**:
- `backend/tests/test_orchestrator_live.py` — **nuevo**, gated por
  `RUN_LIVE_GEMINI_TESTS=1`: crear sesión → "hola, quiero un seguro para mi casa,
  vivo en casa propia estrato 3 en Bogotá, tengo 35 años" → asserts tolerantes: la
  respuesta no es el fallback, y tras 2-3 turnos guiando a cotizar, si la sesión tiene
  `quote`, su prima == motor exacto (el LLM no la alteró).

**Impacto en contrato API (front↔back)**: No.
**Acciones**: implementar + una corrida live manual.
**Pruebas / verificación**: suite normal verde (live saltados); corrida live verde.
**Riesgos**: no-determinismo del LLM → asserts sobre datos del motor y estructura,
jamás sobre prosa; si el arco no se completa en 3 turnos, el test valida lo que sí
ocurrió (tolerante) — la validación fina del tono es manual en el chat.

🛑 **CHECKPOINT** — fin del plan.
**Commit sugerido**: `test(back): add gated live check for orchestrator flow`
