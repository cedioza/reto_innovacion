# Plan — F1: Webhooks conectados al orquestador (contrato de adaptador + Meta) · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-26 · **Tipo**: plan de implementación por fases.
> **Base**: [20260725-a3-orquestador-conversacional-llm.plan.md](.claude/analysis/plans/20260725-a3-orquestador-conversacional-llm.plan.md)
> (el orquestador LLM al que se conectan los canales),
> [20260725-c3-conversaciones-solicitudes-postgres.plan.md](.claude/analysis/plans/20260725-c3-conversaciones-solicitudes-postgres.plan.md)
> (tabla `sesiones_canal` + dedupe persistido — la base del "retoma tras redeploy").
> Tarea del brain: **F1 — Webhooks conectados al orquestador** (depende de A3 ✔;
> bloquea F2, E4, F4 y F5). Decisión de negocio: DEC-008 (Meta con YCloud de
> respaldo); doctrina: "adaptador delgado por canal desde el primer commit".
> **Proyectos afectados**: backend.
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

Definir el **contrato único de adaptador de canal** — entrada: payload crudo →
`(canal, user_ref, texto)`; salida: texto del agente → mensajes del canal (división
por límite + formato propio) — y conectar el primer canal real a través de él:
**WhatsApp vía Meta Cloud API**, hablando con el agente LLM (orquestador A3) en vez
del `ChannelHandler` de keywords. Todo lo demás (sesión, LLM, tools, guardrails)
queda detrás de un `handle(canal, user_ref, texto)` que NO cambia al agregar
canales — F4 (YCloud) y F5 (Telegram) son la prueba de que el contrato quedó bien.

## Contexto / hallazgos del análisis

**Lo que hay hoy (post-merges del 26-jul):**

- Los 3 webhooks ([webhooks.py](backend/app/api/routes/webhooks.py)) hacen parsing
  inline del payload y llaman `_handler.handle_incoming(canal, user_ref, texto)` —
  el [ChannelHandler](backend/app/services/channel_handler.py) de regex/keywords
  (flujo rígido de formulario), NO el orquestador LLM. Meta:
  [webhooks.py:65-66](backend/app/api/routes/webhooks.py#L65-L66); YCloud:
  [:129-134](backend/app/api/routes/webhooks.py#L129-L134) (con dedupe persistido
  vía handler); Telegram: [:155](backend/app/api/routes/webhooks.py#L155).
- **No existe** `orchestrator.handle(canal, user_ref, texto)`:
  [orchestrator.respond(session_id, content)](backend/app/services/orchestrator.py#L318)
  es el turno LLM completo (tools, guardrails, tarjetas, persistencia) pero habla en
  `session_id`, no en `(canal, user_ref)`.
- **El mapeo canal+teléfono→sesión ya persiste**:
  [ChannelSessionRepository](backend/app/repositories/channel_sessions.py) (C3,
  tabla `sesiones_canal`, PK compuesta canal+user_ref) — hoy solo lo usa el
  ChannelHandler. El "retoma tras redeploy" es componer esto con `respond` (las
  conversaciones ya sobreviven por C3).
- **Salida por canal**: [whatsapp_provider.send_whatsapp_message](backend/app/services/whatsapp_provider.py#L8)
  ya alterna Meta/YCloud por env (`WHATSAPP_PROVIDER`); no hay división por límite
  de caracteres (WhatsApp corta en 4096) ni conversión de formato (el LLM emite
  markdown `**negrita**`; WhatsApp usa `*negrita*`).
- `respond` devuelve la **sesión completa**; el texto del turno son los mensajes
  assistant agregados en ese turno (texto final + resúmenes de tarjeta de una línea
  generados por código — [orchestrator.py:450-455](backend/app/services/orchestrator.py#L450)).
  El gateway puede tomar el delta de mensajes (conteo antes/después del turno) —
  determinista, sin heurísticas.
- **Cuota Gemini**: sin `GEMINI_API_KEY` el orquestador respondería siempre el
  fallback — inaceptable como default de dev. El ChannelHandler regex queda como
  **fallback automático cuando no hay key** (y documentado hasta H5, como pide la
  tarea).
- **Tests que tocan este camino** (mockean `_handler.handle_incoming` o el envío):
  [test_ycloud_webhooks.py](backend/tests/test_ycloud_webhooks.py),
  [test_telegram_webhook.py](backend/tests/test_telegram_webhook.py),
  [test_closing_cards.py](backend/tests/test_closing_cards.py),
  [test_shared_conversation_state.py](backend/tests/test_shared_conversation_state.py).
  F1 solo re-cablea el webhook de **Meta** — YCloud y Telegram siguen por el
  handler legacy hasta F4/F5, así que sus tests no deberían moverse.
- Regla de capas: el router no toca repositorios → el gateway es un **service**
  (`channel_gateway`) que posee `ChannelSessionRepository` y compone
  `conversation_service` + `orchestrator.respond` (patrón orquestador permitido).
  El nombre `orchestrator.handle` de la tarea se materializa como
  `channel_gateway.handle` para no mezclar el loop LLM con el ruteo de canal
  (decisión documentada abajo).

## Decisiones pendientes (bloqueantes)

(ninguna — resueltas en el análisis:)

- **`handle` vive en `app/services/channel_gateway.py`**, no dentro de
  `orchestrator.py`: orquestador = loop LLM puro; gateway = sesión-por-canal +
  turno + delta de respuesta. El contrato público es el de la tarea:
  `handle(canal, user_ref, texto) -> str`.
- **Fallback sin key**: si `settings.gemini_api_key` está vacía, `handle` delega en
  el `ChannelHandler` regex (dev sin key sigue funcionando; con key, canal LLM).
  Cero env vars nuevas. El ChannelHandler NO se borra (eso es H5).
- **El adaptador es dueño del formato**: división en mensajes ≤4096 (por párrafos,
  sin cortar palabras) y `**bold**`→`*bold*` viven en el adaptador de WhatsApp; el
  orquestador no sabe de canales.
- **Solo Meta se re-cablea en F1**. YCloud (F4) y Telegram (F5) siguen por el
  camino legacy — el criterio 3 ("agregar canal no toca el core") se demuestra con
  un test de canal ficticio y se confirma al ejecutar F4/F5.

## Principios

- Verde por fase: `.venv\Scripts\python.exe -m pytest -q` desde `backend/`; tests
  de conversación siempre con LLM mockeado (patrón `_scripted_llm`) — cero cuota.
- Contrato HTTP externo intacto: las rutas de webhook, sus verificaciones de
  firma/secret y sus respuestas (`{"status": "ok"}`, 200 siempre ante payload raro)
  no cambian — lo que cambia es el cerebro detrás.
- Aditivo antes que destructivo: primero el contrato+gateway (nada se rompe), luego
  el re-cableo de Meta; el handler legacy queda como fallback documentado.
- Cero dependencias nuevas, cero env vars nuevas.

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | backend | Ninguno | 5m | _(sin commit)_ |
| 1 | Contrato de adaptador + channel gateway | backend | Aditivo | 35m | `feat(channels): add channel adapter contract and gateway` |
| 2 | Adaptador Meta + webhook por el orquestador | backend | Medio | 35m | `feat(channels): route meta whatsapp webhook through llm` |

Total estimado: ~75m (estimación del brain: 2h).

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: backend
**Objetivo**: baseline verde y confirmación de los puntos de enganche.
**Archivos afectados**: ninguno (solo lectura).
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` (anotar el baseline
   exacto — la suite viene moviéndose con los merges; hay 2 fallos conocidos de
   Resend/E6 según el brain: si aparecen, anotarlos como preexistentes y NO
   atribuirlos a F1).
2. Confirmar qué asserts hacen los tests de webhooks/cards sobre
   `_handler.handle_incoming` (qué habría que re-mockear en Fase 2 para el camino
   Meta).
3. Confirmar el shape del payload Meta que el webhook parsea hoy (texto e
   interactive/button_reply — [webhooks.py:37-67](backend/app/api/routes/webhooks.py#L37-L67)).
**Pruebas / verificación**: suite corrida y baseline anotado.
**Riesgos**: fallos preexistentes ajenos (Resend/E6) — se documentan, no se tocan.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit — fase de solo lectura)_

---

## Fase 1 — Contrato de adaptador + channel gateway

**Proyecto**: backend
**Objetivo**: la "pieza de lego" existe y está probada: entrada normalizada, salida
formateada por canal, y un `handle(canal, user_ref, texto)` canal-agnóstico que
resuelve sesión persistida y corre el turno LLM.
**Archivos afectados**:
`backend/app/services/channels/__init__.py` (nuevo) ·
`backend/app/services/channels/base.py` (nuevo) ·
`backend/app/services/channel_gateway.py` (nuevo) ·
`backend/tests/test_channel_gateway.py` (nuevo)
**Impacto en contrato API (front↔back)**: No (infraestructura interna; ningún
webhook cambia aún).
**Acciones**:
1. `channels/base.py`: dataclass `InboundMessage(channel, user_ref, text)`; contrato
   `ChannelAdapter` (Protocol o ABC mínima): `channel: str`,
   `parse_incoming(payload: dict) -> InboundMessage | None` (None = evento a
   ignorar) y `deliver(user_ref: str, text: str) -> bool`; helpers puros
   compartidos: `split_text(text, limit)` (por párrafos/renglones, sin cortar
   palabras, siempre ≤limit) y `markdown_bold_to_whatsapp(text)` (`**x**` → `*x*`).
   Docstring en español: el contrato que hace de F4/F5 tareas de 1 hora.
2. `channel_gateway.py`: `handle(channel, user_ref, text) -> str` —
   (a) sin `settings.gemini_api_key` → delega en el `ChannelHandler` legacy
   (fallback documentado hasta H5) y retorna;
   (b) con key: resuelve `session_id` en `ChannelSessionRepository` (crea
   conversación nueva vía `conversation_service.create` + `save` del mapeo si no
   hay, o si la sesión apuntada ya no existe);
   (c) toma el conteo de mensajes previo, llama `orchestrator.respond(session_id,
   text)`, y devuelve el texto del turno: mensajes assistant nuevos concatenados
   (`\n\n`) usando `content` (los card-messages aportan su resumen de una línea).
   `canal` forma parte de la clave de sesión — el gateway jamás inspecciona el
   nombre del canal.
3. Tests (TDD-light) en `test_channel_gateway.py` (patrón `_scripted_llm` + engine
   in-memory del conftest):
   - Turno feliz: canal `"whatsapp"`, user nuevo → crea conversación, responde el
     texto guionado, y `sesiones_canal` quedó con el mapeo.
   - Continuidad: segundo `handle` del mismo user reutiliza el MISMO `session_id`
     (y el historial crece) — y con un repo/gateway recreado sobre el mismo engine
     (simula redeploy) el user retoma su conversación (criterio 2).
   - **Canal-agnóstico (criterio 3)**: `handle("canal-inventado", ...)` funciona
     idéntico — ninguna rama por nombre de canal.
   - Fallback: sin key Gemini → la respuesta viene del ChannelHandler (mock/espía)
     y no se llama al LLM.
   - Helpers: `split_text` nunca excede el límite ni corta palabras; texto corto →
     1 mensaje; `markdown_bold_to_whatsapp` convierte `**x**` y no toca `*x*`.
**Pruebas / verificación**: pytest verde (suite completa; los tests nuevos no
gastan cuota).
**Riesgos**: sesión apuntada por `sesiones_canal` borrada a mano → `handle` debe
recrear en vez de explotar (test de sesión huérfana).

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `feat(channels): add channel adapter contract and gateway`

---

## Fase 2 — Adaptador Meta + webhook por el orquestador

**Proyecto**: backend
**Objetivo**: el webhook de Meta habla con el agente LLM vía el contrato — primera
conversación real de WhatsApp sin el formato rígido (criterio 1).
**Archivos afectados**:
`backend/app/services/channels/meta_whatsapp.py` (nuevo) ·
[webhooks.py](backend/app/api/routes/webhooks.py) (solo el bloque Meta) ·
`backend/tests/test_meta_channel_adapter.py` (nuevo) ·
[test_closing_cards.py](backend/tests/test_closing_cards.py) /
[test_shared_conversation_state.py](backend/tests/test_shared_conversation_state.py)
(solo si mockeaban el camino Meta — según pre-flight)
**Impacto en contrato API (front↔back)**: No para el frontend web; el contrato
EXTERNO del webhook Meta (ruta, verify GET, 200 siempre) se conserva — cambia el
motor de respuesta (keywords → LLM). YCloud y Telegram intactos (F4/F5).
**Acciones**:
1. `channels/meta_whatsapp.py` — `MetaWhatsAppAdapter` implementando el contrato:
   - `parse_incoming(payload)`: el parsing EXACTO que hoy vive inline en
     [webhooks.py:39-64](backend/app/api/routes/webhooks.py#L39-L64) (entry/changes/
     value/messages, tipos `text` e `interactive.button_reply`), devolviendo
     `InboundMessage("whatsapp", phone, texto)` o None.
   - `deliver(user_ref, text)`: `markdown_bold_to_whatsapp` + `split_text(4096)` +
     un `send_whatsapp_message` (provider actual) por trozo, en orden; False si
     algún envío falla.
2. `webhooks.py` — el POST de Meta pasa a: `inbound = adapter.parse_incoming(...)`
   → si None, `{"status": "ok"}`; si hay texto →
   `respuesta = channel_gateway.handle(inbound.channel, inbound.user_ref,
   inbound.text)` → `adapter.deliver(...)`. El try/except envolvente (200 siempre)
   y el GET de verificación quedan intactos. YCloud/Telegram no se tocan.
3. Tests (TDD-light) en `test_meta_channel_adapter.py`:
   - `parse_incoming`: payload real de texto → InboundMessage correcto; payload de
     botón interactivo → texto del botón; payload sin mensajes / malformado → None
     (y el webhook responde 200, nunca 500).
   - `deliver`: texto de 9000 chars → N envíos todos ≤4096 en orden; `**negrita**`
     llega como `*negrita*`; fallo de envío → False.
   - Webhook e2e con gateway mockeado: POST payload Meta → se llamó
     `handle("whatsapp", phone, texto)` y se entregó la respuesta; POST basura →
     200.
   - Ajustar los tests legacy SOLO si mockeaban el camino Meta (pre-flight lo
     dice); no debilitar ninguno.
4. Documentar en el README del backend (sección canales, breve): el contrato, el
   fallback regex (hasta H5) y la deuda "YCloud/Telegram al contrato en F4/F5".
**Pruebas / verificación**: pytest completo verde. **Manual (criterio 1, requiere
número de prueba Meta + key Gemini — anotar como pendiente si no hay entorno)**:
conversación real por WhatsApp de punta a punta; reiniciar backend a mitad y
verificar que el mismo teléfono retoma (criterio 2 en vivo — la versión de test ya
quedó en Fase 1).
**Riesgos**: latencia del LLM en el webhook (Meta reintenta si no respondes
rápido) — el handler corre en threadpool como hoy y el 200 se responde al final
del turno; si en la práctica Meta reintenta, el dedupe por `message.id` es
follow-up de F3/F4, anotado en el README.

🛑 **CHECKPOINT FINAL** — F1 cumple: contrato demostrado canal-agnóstico (test de
canal ficticio + F4/F5 como prueba real), WhatsApp Meta al LLM, sesiones que
sobreviven redeploy. Marcar F1 en el brain; desbloquea F2, E4, F4, F5.
**Commit sugerido**: `feat(channels): route meta whatsapp webhook through llm`
