# Plan — D3: Tarjetas de recomendación, cotización y comparador · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-25 · **Tipo**: plan de implementación por fases.
> **Base**: [20260725-d2-chat-conectado-orquestador.plan.md](.claude/analysis/plans/20260725-d2-chat-conectado-orquestador.plan.md)
> (chat conectado al orquestador; `useChat` sincroniza desde `session.messages`),
> [20260725-a3-orquestador-conversacional-llm.plan.md](.claude/analysis/plans/20260725-a3-orquestador-conversacional-llm.plan.md)
> (loop de tools del orquestador) y
> [20260725-a5-guardrails-y-confirmaciones.plan.md](.claude/analysis/plans/20260725-a5-guardrails-y-confirmaciones.plan.md)
> (guard mecánico de precios — este plan corrige un caso latente suyo).
> Tarea del vault: `07 - Tareas/Feature D - Chat web/D3 - Tarjetas de recomendacion cotizacion y comparador.md`
> (depende de D2 ✅; bloquea D4). Relación con B4 (multicategoría, pendiente): NO es
> prerequisito — el comparador de D3 compara la cotización actual vs una propuesta con
> otros ajustes del mismo producto, que es lo que el motor de hoy sabe hacer.
> **Proyectos afectados**: ambos (backend primero: el contrato de tarjetas y el
> endpoint de ajustes deben existir antes de que el front los pinte).
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

Los momentos clave del funnel se renderizan como **tarjetas ricas** dentro del chat:
recomendación con las razones del motor visibles ("por qué este seguro para ti"),
cotización con prima/coberturas/exclusiones (colapsables), y comparador de 2 opciones
(actual vs propuesta) con toggles de ajustes que **recotizan vía API sin recargar** y
sin pasar por el LLM. Materializa en pantalla la lógica explicable — el criterio no
negociable del reto — y es la pantalla que más aparece en el video del pitch.

Criterios de aceptación del vault:
1. La recomendación muestra ≥2 razones legibles para no técnicos.
2. Activar un ajuste en el comparador recotiza y actualiza el precio sin recargar.
3. Las exclusiones son visibles sin scroll infinito (colapsable).

## Contexto / hallazgos del análisis

**Todo dato de tarjeta ya existe en el backend — falta transportarlo como tarjeta:**

- [orchestrator.py:374](backend/app/services/orchestrator.py#L374) — el loop ejecuta
  las tools y sus resultados viajan al LLM, pero **solo se persiste texto**:
  [orchestrator.py:401-402](backend/app/services/orchestrator.py#L401-L402) agrega
  `Message(role, content)` planos. El vault pide marcar mensajes con
  `type: recommendation|quote|comparison` + payload estructurado.
- [conversation.py:15](backend/app/schemas/conversation.py#L15) — `Message` solo tiene
  `role` y `content`. Extensión aditiva: `type: str = "text"` +
  `payload: dict | None = None` (los mensajes existentes siguen válidos).
- Payloads ya calculados por el motor:
  - Recomendación: `PropensityService.evaluate` → `reasons` =
    `[{code, label, evidence}]` ([propensity.py:23-27](backend/app/services/propensity.py#L23-L27))
    — `label` + `evidence` son exactamente las "razones legibles" del criterio 1.
  - Cotización: `QuoteService.calculate_quote` → prima, coberturas, exclusiones,
    ajustes ([quote.py:55-63](backend/app/services/quote.py#L55-L63)).
  - Comparación: la tool `ajustar_comparar` ya devuelve
    `{actual, propuesta, diferencia_mensual, ajustes_disponibles}`
    ([agent_tools.py:292-297](backend/app/services/agent_tools.py#L292-L297)).
- [orchestrator.py:107-115](backend/app/services/orchestrator.py#L107-L115) —
  `_contents_from_history` reconstruye el historial del LLM desde `session.messages`:
  los mensajes-tarjeta deben **excluirse** de ahí (el estado del funnel ya se inyecta
  vía `_build_status_summary`; un payload JSON en el historial solo quema tokens).
- [conversations.py:63](backend/app/api/routes/conversations.py#L63) es el único
  caller de `respond()` — los webhooks aún no están conectados al orquestador (F1 del
  vault pendiente), así que el cambio de contrato solo lo ve el chat web.

**🐛 Bug latente del guard de precios que el comparador dispararía** (se corrige aquí):

- `QuoteService` devuelve `annual_premium`, pero
  [`QuoteDetail`](backend/app/schemas/conversation.py#L34-L40) **no tiene ese campo**
  → se pierde al persistir la sesión. En turnos posteriores el guard reconstruye las
  cifras permitidas desde `session.quote`
  ([orchestrator.py:244-258](backend/app/services/orchestrator.py#L244-L258), que SÍ
  lista `annual_premium`) — hoy no explota porque sin ajustes
  `annual == base_amount` (45.000). **Con un ajuste activo** (p. ej. `fire_alarm`,
  modifier 0.85 → anual 38.250 ≠ base 45.000), si el LLM cita la prima anual en un
  turno posterior el guard la bloquearía **injustamente**. Fix: agregar
  `annual_premium: Optional[float]` a `QuoteDetail` (el filtro de
  [orchestrator.py:172-177](backend/app/services/orchestrator.py#L172-L177) lo
  propaga solo).

**El toggle del comparador NO debe pasar por el LLM:**

- Latencia 8-12 s + 1-3 llamadas de cuota por turno vs. un recálculo determinista de
  milisegundos. El criterio 2 ("recotiza sin recargar") pide un endpoint REST directo.
- [conversation.py (service)](backend/app/services/conversation.py) ya compone
  `QuoteService` (regla de capas ✓) — el lugar natural para `apply_adjustments()`.
- Coherencia con el LLM garantizada por diseño: `respond()` reconstruye el
  `ToolContext` desde la sesión en cada turno
  ([orchestrator.py:337](backend/app/services/orchestrator.py#L337)), así que una
  cotización actualizada por REST es la que el agente cita en el siguiente turno (el
  status summary la inyecta).
- Ajustes del catálogo hoy ([catalog.py:60-79](backend/app/repositories/catalog.py#L60-L79)):
  `fire_alarm` (0.85), `security_system` (0.80), `high_value` (1.25) — suficientes
  para un comparador con toggles real.

**Frontend (D2) — el riel ya está puesto:**

- [useChat.js:17-21](frontend/src/features/chat/composables/useChat.js#L17-L21) —
  `mapSessionMessages` reconstruye burbujas desde `session.messages`; extenderlo para
  pasar `type`/`payload` es un cambio local. La reconstrucción `[...prefix, ...map]`
  hace que las tarjetas se posicionen y rehidraten solas (F5 incluido).
- [ChatView.vue:35](frontend/src/features/chat/ChatView.vue#L35) — renderiza todo con
  `MessageBubble`; pasará a elegir componente por `message.type`.
- [api.js](frontend/src/shared/services/api.js) — patrón listo para
  `postAdjustments()`; los errores ya traen `status` y timeout.
- Regla del front: componentes de la feature en `features/chat/components/` ✓, HTTP
  solo vía `shared/services/` ✓, sin dependencias UI nuevas (CSS propio como D1).

**Decisiones resueltas en el análisis:**

1. **Mensajes-tarjeta en la transcripción** (no campos sueltos de sesión): las
   tarjetas quedan posicionadas en el hilo, se rehidratan gratis con el flujo de D2 y
   son la transcripción trazable del pitch. `content` lleva un resumen de una línea
   generado por código (p. ej. "📋 Cotización: $3.750 COP/mes") como fallback legible
   para consumidores sin soporte de tarjetas.
2. **Las tarjetas se emiten después del texto del asistente** en el mismo turno, una
   por tool ejecutada (si una tool corrió varias veces en el turno, vale el último
   resultado). El texto explica; la tarjeta evidencia.
3. **El endpoint de ajustes devuelve la sesión completa** (`ConversationResponse`,
   mismo shape que `/message`): el front reutiliza intacta la sincronización de D2. Y
   **actualiza in-place el último mensaje `comparison`** (o lo agrega si no hay):
   cada toggle NO apila una tarjeta nueva — el comparador es una tarjeta viva.
4. **Códigos de ajuste desconocidos → 400** (hoy `QuoteService` los ignora en
   silencio): el toggle del front solo manda códigos de `ajustes_disponibles`, así que
   un código inválido es un bug o un curl manual — mejor explícito.
5. **El comparador nace de dos caminos**: por conversación (el LLM llama
   `ajustar_comparar` → tarjeta `comparison`) o por botón "Ajustar coberturas" en la
   `QuoteCard` (llama al endpoint con `[]` → aparece el comparador con los toggles
   disponibles y diferencia 0). Así el criterio 2 es demostrable sin depender de que
   el jurado escriba "quiero comparar".

## Decisiones pendientes (bloqueantes)

(ninguna — las 5 de diseño quedaron resueltas arriba.)

## Principios

- Backend primero (contrato de tarjetas → endpoint de ajustes), frontend después.
- **El front nunca calcula precios**: todo dato visible viene del payload del motor
  (`diferencia_mensual` incluida — viene calculada del backend).
- Cambios de contrato **aditivos**: `type`/`payload` con defaults; los mensajes y
  consumidores existentes siguen funcionando sin tocarse.
- Verde por fase: pytest (backend) / `npm run build` (frontend); TDD-light en fases
  de backend.
- El toggle recotiza por REST determinista — cero llamadas al LLM, cero cuota.
- Sin dependencias nuevas, sin env vars nuevas. CSS propio (línea de D1).

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | ambos | Ninguno | 5m | _(sin commit)_ |
| 1 | Backend: mensajes-tarjeta tipados + fix `annual_premium` | backend | Medio (contrato aditivo) | 30m | `feat(back): emit typed card messages from orchestrator` |
| 2 | Backend: endpoint de ajustes con comparación | backend | Medio (ruta nueva) | 25m | `feat(back): add adjustments endpoint with quote compare` |
| 3 | Frontend: `RecommendationCard` + `QuoteCard` en el chat | frontend | Alto (UI del pitch) | 35m | `feat(front): render recommendation and quote cards` |
| 4 | Frontend: `CompareCard` con toggles que recotizan | frontend | Alto (criterio 2) | 35m | `feat(front): add compare card with live adjustments` |

Total: ~130m. Si el sábado aprieta: la Fase 4 es recortable a "comparador solo por
conversación" (tarjeta `comparison` estática sin toggles) sin tocar las fases 1-3.

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: ambos
**Objetivo**: punto de partida verde.
**Archivos afectados**: ninguno.
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Backend desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` → línea base
   (227 passed + 9 skipped si D2 ya está en master; registrar la que aparezca).
2. Frontend desde `frontend/`: `npm run build` → OK.
3. Confirmar con `git log` que D2 (`plan/d2-chat-conectado-orquestador`) ya está
   mergeado en master — **este plan construye encima de su `useChat`**; si no está,
   ⛔ resolver antes de ejecutar (mergear el PR de D2 primero).

**Pruebas / verificación**: las de arriba.
**Riesgos**: ninguno.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit)_

---

## Fase 1 — Backend: mensajes-tarjeta tipados + fix `annual_premium`

**Proyecto**: backend
**Objetivo**: la transcripción transporta tarjetas: cada tool clave ejecutada deja un
mensaje tipado con el payload del motor, sin contaminar el historial del LLM. De paso
se corrige el bug latente del guard con la prima anual.
**Archivos afectados**:
- [conversation.py (schemas)](backend/app/schemas/conversation.py) — `Message` gana
  `type: str = "text"` y `payload: Optional[dict] = None`; `QuoteDetail` gana
  `annual_premium: Optional[float] = None`.
- [orchestrator.py](backend/app/services/orchestrator.py) — en el loop de tools,
  registrar el último resultado de `recomendar_seguro`, `cotizar` y
  `ajustar_comparar` (patrón de `cerrar_venta_result`); tras el
  `Message(role="assistant", ...)` final, agregar los mensajes-tarjeta en orden
  (recommendation → quote → comparison) con `content` = resumen de una línea generado
  por código; `_contents_from_history` pasa a incluir SOLO mensajes `type == "text"`.
  El payload de `recommendation` incluye `product_name` (vía `CatalogService`, como
  hace `_sync_ctx_to_session`); el de `quote` es el dict completo del motor (con
  `annual_premium`); el de `comparison` es el resultado de la tool tal cual.
- Tests (nuevos + ajustes, patrón LLM guionizado de
  [test_orchestrator.py](backend/tests/test_orchestrator.py)):
  - turno que ejecuta `cotizar` → `session.messages` termina con mensaje
    `type="quote"` cuyo payload trae las cifras exactas del motor y `content` legible
    no vacío;
  - turno que ejecuta `recomendar_seguro` → tarjeta `recommendation` con ≥2 `reasons`
    (label + evidence);
  - los mensajes-tarjeta NO aparecen en los `contents` enviados al LLM en el turno
    siguiente (espiar el `generate_reply` guionizado);
  - `QuoteDetail` con ajuste activo persiste `annual_premium`, y una respuesta
    posterior que cite la prima anual ajustada pasa el guard (el caso 38.250 vs
    45.000 de arriba);
  - regresión: mensajes `type="text"` siguen comportándose igual (suite previa verde).

**Impacto en contrato API (front↔back)**: **Sí — aditivo.** `Message` gana `type` y
`payload` (defaults compatibles: los mensajes de texto no cambian); `QuoteDetail` gana
`annual_premium`. Ninguna ruta ni status code cambia. **Quién actualiza el otro
lado**: Fases 3-4 (front, este mismo plan). El front actual (D2) ignora los campos
nuevos sin romperse — renderizaría las tarjetas como burbujas con el `content` de
fallback hasta la Fase 3.
**Acciones**:
1. TDD-light: tests primero (fallan porque no existen `type`/`payload`/tarjetas).
2. Implementar schemas + orquestador.
3. Suite completa verde.

**Pruebas / verificación**: pytest verde (línea base + nuevos); manual opcional:
uvicorn + un `POST /message` real y ver el mensaje `type="quote"` en la respuesta
(gasta 1-3 req de cuota — solo si hay cuota disponible).
**Riesgos**: el orden texto→tarjetas debe ser estable para que el front pinte
consistente; si el LLM no llama tools en el turno (charla), no hay tarjetas — correcto
por diseño.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `feat(back): emit typed card messages from orchestrator`

---

## Fase 2 — Backend: endpoint de ajustes con comparación

**Proyecto**: backend
**Objetivo**: el toggle del comparador recotiza en milisegundos por REST determinista,
manteniendo al LLM coherente con el precio vigente.
**Archivos afectados**:
- [conversation.py (schemas)](backend/app/schemas/conversation.py) — schema nuevo
  `AdjustmentsRequest { adjustments: list[str] }`.
- [conversation.py (service)](backend/app/services/conversation.py) — método
  `apply_adjustments(session_id, adjustments) -> ConversationResponse`:
  - sesión inexistente → `ValueError("Session not found")` (la ruta lo vuelve 404);
  - sin `profile` o sin `quote` previa → `ValueError` de negocio (→ 400: no hay nada
    que ajustar antes de cotizar);
  - código de ajuste no presente en el catálogo → `ValueError` (→ 400, decisión 4);
  - recalcula con `self._quote.calculate_quote(session.profile, adjustments)`, arma
    el payload `{actual, propuesta, diferencia_mensual, ajustes_disponibles}` (mismo
    shape que la tool `ajustar_comparar`), asigna `session.quote = propuesta` (con
    `annual_premium`), **actualiza in-place el último mensaje `type="comparison"`**
    (o lo agrega al final si no existe) y persiste.
- [conversations.py (routes)](backend/app/api/routes/conversations.py) — ruta nueva
  `POST /conversations/{session_id}/adjustments` → `ConversationResponse` (200; 404 /
  400 / 422 en negativos), delgada como las demás.
- Tests: happy path (aplicar `fire_alarm` → prima propuesta 0.85×, `diferencia_mensual`
  negativa exacta del motor, `session.quote` actualizado, tarjeta `comparison`
  presente y única tras 2 llamadas seguidas); negativos: 404 sesión inexistente, 400
  sin cotización previa, 400 código desconocido, 422 body inválido; coherencia LLM:
  tras ajustar por REST, el siguiente `respond()` guionizado recibe en su status
  summary la prima nueva (y el guard permite citarla).

**Impacto en contrato API (front↔back)**: **Sí — ruta nueva**
`POST /api/v1/conversations/{id}/adjustments` (aditiva; nada existente cambia).
**Quién actualiza el otro lado**: Fase 4 (front, este plan).
**Acciones**:
1. TDD-light: tests primero.
2. Schema + service + ruta.
3. Suite completa verde.

**Pruebas / verificación**: pytest verde; manual: uvicorn + crear sesión + simular
cotización previa (o sesión real si hay cuota) + `curl POST .../adjustments` con
`{"adjustments":["fire_alarm"]}` → 200 con `comparison` y prima 0.85×; curl con código
inventado → 400; sin sesión → 404. Cero llamadas al LLM en este endpoint.
**Riesgos**: doble fuente de escritura de `session.quote` (LLM y REST) — mitigado por
diseño: ambos escriben la misma sesión y el ctx se reconstruye por turno; el test de
coherencia lo fija.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 3 sin aprobación del usuario.
**Commit sugerido**: `feat(back): add adjustments endpoint with quote compare`

---

## Fase 3 — Frontend: `RecommendationCard` + `QuoteCard` en el chat

**Proyecto**: frontend
**Objetivo**: los momentos de recomendación y cotización dejan de ser texto plano —
la lógica explicable del motor, visible (criterios 1 y 3). La pantalla del pitch.
**Archivos afectados**:
- [useChat.js](frontend/src/features/chat/composables/useChat.js) —
  `mapSessionMessages` propaga `type` y `payload` al objeto de mensaje (los `text`
  quedan igual).
- [ChatView.vue](frontend/src/features/chat/ChatView.vue) — elegir componente por
  `message.type`: `recommendation` → `RecommendationCard`, `quote` → `QuoteCard`,
  `comparison` → (Fase 4; mientras tanto cae a `MessageBubble` con el `content`
  fallback), resto → `MessageBubble`.
- Nuevos en [frontend/src/features/chat/components/](frontend/src/features/chat/components/):
  - `RecommendationCard.vue` — nombre del producto + razones como lista/chips:
    `label` en grande, `evidence` como detalle (≥2 razones legibles — criterio 1);
    estética alineada a `chat-theme.css` (verde institucional, burbuja ancha del lado
    del bot).
  - `QuoteCard.vue` — prima mensual grande (formato COP con separador de miles, tal
    cual viene del payload), prima anual secundaria, coberturas como lista, y
    **exclusiones + detalle de ajustes en `<details>` colapsable** (criterio 3, sin
    JS extra); botón "Ajustar coberturas" presente pero se cablea en la Fase 4
    (emite evento; en esta fase puede quedar oculto o deshabilitado).
**Impacto en contrato API (front↔back)**: No (consume el contrato de la Fase 1).
**Acciones**:
1. Extender el mapeo en `useChat` (conservando timestamps/rehidratación de D2).
2. Crear las 2 tarjetas + selección por tipo en `ChatView`.
3. `npm run build` OK.

**Pruebas / verificación**: `npm run build`; manual con backend levantado (1
conversación real si hay cuota, o sesión sembrada por los endpoints estructurados
`POST /profile` para no gastar LLM): la recomendación aparece como tarjeta con ≥2
razones, la cotización con prima grande y exclusiones colapsadas por defecto; F5 →
las tarjetas se rehidratan en su posición (payload persistido); API caída → el flujo
de error amable de D2 intacto.
**Riesgos**: es la fase de gusto visual (el vault advierte contra el look "generado
por IA sin criterio") — mantener la paleta de D1 y revisar en ancho móvil (~375px);
mensajes-tarjeta sin payload esperado (defensa: si `payload` falta, caer a
`MessageBubble` con el content fallback, nunca pantalla rota).

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 4 sin aprobación del usuario.
**Commit sugerido**: `feat(front): render recommendation and quote cards`

---

## Fase 4 — Frontend: `CompareCard` con toggles que recotizan

**Proyecto**: frontend
**Objetivo**: criterio 2 — activar un ajuste recotiza y actualiza el precio sin
recargar (y sin LLM).
**Archivos afectados**:
- [api.js](frontend/src/shared/services/api.js) — función nueva
  `postAdjustments(sessionId, adjustments)` →
  `api.post(\`/api/v1/conversations/${sessionId}/adjustments\`, { adjustments })`.
- [useChat.js](frontend/src/features/chat/composables/useChat.js) — acción
  `applyAdjustments(codes)`: llama `postAdjustments` y re-sincroniza `messages` desde
  la sesión devuelta (mismo camino que `sendMessage`, sin typing del LLM; un flag
  local `isAdjusting` para el spinner del card); error → burbuja amable de D2 (el
  toggle vuelve a su estado según el payload vigente).
- `CompareCard.vue` (nuevo en `features/chat/components/`) — 2 columnas
  actual/propuesta (prima mensual de cada una), `diferencia_mensual` destacada con
  signo (viene calculada del motor — el front no resta), y toggles construidos desde
  `ajustes_disponibles` marcando activos los códigos presentes en
  `propuesta.adjustments`; al toggle → `applyAdjustments` con el set resultante;
  estado ocupado mientras responde.
- [ChatView.vue](frontend/src/features/chat/ChatView.vue) — `comparison` →
  `CompareCard`; cablear el botón "Ajustar coberturas" de `QuoteCard` →
  `applyAdjustments([])` (hace aparecer el comparador con toggles y diferencia 0,
  decisión 5).
**Impacto en contrato API (front↔back)**: No cambia el contrato (consume la ruta de
la Fase 2).
**Acciones**:
1. `postAdjustments` en `api.js`.
2. `applyAdjustments` en `useChat` + `CompareCard` + cableado en `ChatView`/`QuoteCard`.
3. `npm run build` OK.

**Pruebas / verificación**: `npm run build`; manual e2e (con cuota: conversación real
hasta la cotización; sin cuota: sembrar con `POST /profile`): botón "Ajustar
coberturas" → aparece el comparador; activar `fire_alarm` → la prima propuesta baja a
0.85× y la diferencia aparece **sin recarga** y en <1s (criterio 2); apagar el toggle
→ vuelve; F5 → el comparador se rehidrata con el último estado (payload actualizado
in-place por el backend); API caída al toggle → mensaje amable, tarjeta no rota;
seguir conversando tras ajustar → el agente cita la prima nueva (coherencia).
**Riesgos**: doble clic rápido en toggles → mitigado con el estado ocupado
(`isAdjusting` deshabilita los toggles durante la llamada); el resto del flujo de
errores ya lo cubre D2.

🛑 **CHECKPOINT** — fin del plan.
**Commit sugerido**: `feat(front): add compare card with live adjustments`

---

## Deuda / fuera de alcance (anotada para el vault)

- **B4 (multicategoría)**: cuando exista, el comparador podrá comparar productos
  distintos — el contrato de tarjeta `comparison` ya lo soporta (2 cotizaciones +
  diferencia), solo cambiará el origen del payload.
- **D4** (cierre en la UI: resumen + consentimiento + éxito) queda desbloqueada; la
  tarjeta natural siguiente es `application` (el shape `ConsentedApplication` ya
  existe en la sesión).
- Los webhooks (F1) heredarán los mensajes-tarjeta en la transcripción: al conectar
  el orquestador, los canales de texto plano deben enviar solo `content` (el fallback
  de una línea ya lo deja resuelto).
- Pulido visual fino y microtextos → H4 (guiones del demo).
