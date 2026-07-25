# Plan — D2: Chat conectado al orquestador · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-25 · **Tipo**: plan de implementación por fases.
> **Base**: [20260725-d1-ui-base-chat-mensajeria.plan.md](.claude/analysis/plans/20260725-d1-ui-base-chat-mensajeria.plan.md)
> (UI del chat, de Cristian — mergeada en `64fe3f2`),
> [20260725-a3-orquestador-conversacional-llm.plan.md](.claude/analysis/plans/20260725-a3-orquestador-conversacional-llm.plan.md)
> (creó `POST /conversations/{id}/message`),
> [20260725-a5-guardrails-y-confirmaciones.plan.md](.claude/analysis/plans/20260725-a5-guardrails-y-confirmaciones.plan.md)
> (guardrails ya en el orquestador) y
> [20260725-api-v1-prefijo-unico.plan.md](.claude/analysis/plans/20260725-api-v1-prefijo-unico.plan.md)
> (todas las rutas bajo `/api/v1`; `api.js` ya sigue la convención).
> Tarea del vault: `07 - Tareas/Feature D - Chat web/D2 - Chat conectado al orquestador.md`
> (depende de D1 ✅ y A3 ✅; bloquea D3 y D5).
> **Proyectos afectados**: frontend (el backend NO se toca — ya expone todo lo necesario).
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

El chat web habla con el backend real: crear conversación, enviar texto libre a
`POST /api/v1/conversations/{id}/message` (orquestador LLM de A3+A5), renderizar la
respuesta del agente con typing indicator, manejar errores de red/timeout con mensajes
amables, y conservar la sesión al recargar la página (`session_id` en localStorage →
rehidratación vía `GET /api/v1/conversations/{id}`).

Criterios de aceptación del vault:
1. Flujo real de punta a punta desde el navegador: saludo → perfil → recomendación → cotización.
2. Recargar la página conserva la conversación.
3. Sin CORS en producción (front y API bajo el mismo dominio — el prefijo `/api/v1` ya lo habilita; la config del proxy es tarea de H1, no de este plan).

## Contexto / hallazgos del análisis

**Backend — ya expone todo lo que D2 necesita (cero cambios):**

- [conversations.py:24](backend/app/api/routes/conversations.py#L24) — `POST /api/v1/conversations`
  (201) crea sesión; `ConversationCreate` tiene todos los campos opcionales → basta `{}`.
- [conversations.py:29](backend/app/api/routes/conversations.py#L29) — `GET /api/v1/conversations/{session_id}`
  (200 / 404) devuelve la sesión completa, incluido `messages` → es la rehidratación.
- [conversations.py:61](backend/app/api/routes/conversations.py#L61) — `POST /api/v1/conversations/{session_id}/message`
  (200 / 404 / 422 si `content` vacío) → el orquestador LLM. Devuelve la sesión
  completa con el historial actualizado.
- [orchestrator.py:401-405](backend/app/services/orchestrator.py#L401-L405) — cada turno
  agrega `Message(role="user"|"assistant", content=...)` y devuelve la sesión: **el
  server es la fuente de verdad del historial**.
- [conversation.py:66](backend/app/schemas/conversation.py#L66) — `ConversationResponse`:
  `session_id`, `state`, `messages[{role, content}]`, `profile`, `recommendation`,
  `quote`, `next_action`. **`Message` NO tiene timestamp ni id** — el front los genera.
- [main.py:14-20](backend/app/main.py#L14-L20) — CORS ya configurado con `FRONTEND_URL`
  (dev: 5173). En producción same-domain, CORS desaparece (DEC-007).
- ⚠️ Persistencia hoy es **en memoria** ([conversation.py:38](backend/app/services/conversation.py#L38),
  C3 del vault sigue pendiente): reiniciar el backend borra las sesiones. Por eso la
  rehidratación debe **degradar con gracia**: `GET` → 404 ⇒ limpiar localStorage y
  arrancar sesión nueva sin romper la UI. Cuando C3 aterrice, este mismo flujo
  sobrevivirá deploys sin tocar el front.

**Frontend — D1 dejó un único punto de conexión:**

- [useChat.js](frontend/src/features/chat/composables/useChat.js) — 100% mock: 3
  mensajes hardcodeados + respuestas aleatorias con `setTimeout`. Expone
  `{ messages, isTyping, sendMessage }` — **el contrato con `ChatView` se conserva**,
  solo cambia la implementación interna.
- [ChatView.vue:8](frontend/src/features/chat/ChatView.vue#L8) — consume el composable;
  deshabilita el input mientras `isTyping`; auto-scroll ya resuelto. No cambia (o
  cambio mínimo si se agrega estado de error).
- [MessageBubble.vue:6](frontend/src/features/chat/components/MessageBubble.vue#L6) —
  shape del front: `{ id, from: 'user'|'bot', text, timestamp }`. Hay que **mapear**
  `role: assistant → from: bot`. `formatTime(undefined)` imprime "Invalid Date" → los
  mensajes rehidratados (sin timestamp del server) necesitan que la hora sea opcional.
- [api.js](frontend/src/shared/services/api.js) — cliente base con `request()`;
  `fetch` **sin timeout** (el LLM puede tardar >10 s con rondas de tools; y un cuelgue
  de red dejaría el typing infinito). D2 del vault pide "timeout con reintento amable".
- `frontend/.env.example` ya documenta `VITE_API_URL` — sin env vars nuevas.

**Reglas que gobiernan** ([frontend/CLAUDE.md](frontend/CLAUDE.md)): HTTP solo vía
`shared/services/` (extender `api.js`, como sugiere el vault); componentes con
`<script setup>`; nada de dependencias nuevas.

**Decisiones resueltas en el análisis:**

1. **Creación de sesión perezosa**: la conversación se crea en el primer
   `sendMessage()` (no al montar la vista) → cero sesiones huérfanas de curiosos que
   solo abren el link. El saludo inicial del bot es una **burbuja local no persistida**
   (texto fijo de bienvenida, como el mock actual) — el historial del server empieza
   con el primer mensaje del usuario.
2. **El server es la fuente de verdad del historial**: tras cada respuesta, `useChat`
   sincroniza su lista desde `session.messages` (mapeando roles). Los timestamps son
   decorativos y solo del cliente: se asignan al momento de recibir cada mensaje; los
   rehidratados tras recarga no tienen (la burbuja oculta la hora si falta).
3. **Timeout de 60 s** en `request()` vía `AbortController` (el orquestador puede
   encadenar hasta 5 rondas de tools + retries de 429). Error/timeout ⇒ burbuja amable
   estilo bot ("Ups, tuve un problema para responderte. Inténtalo de nuevo en un
   momento 🙏"), `isTyping` off, input habilitado. Sin reintento automático (evita
   duplicar mensajes y quemar cuota).
4. **Recuperación de 404 en pleno chat** (backend reiniciado, sesión en memoria
   perdida): limpiar localStorage, crear sesión nueva y reenviar ese mismo mensaje una
   única vez, transparente para el usuario.

## Decisiones pendientes (bloqueantes)

(ninguna — las 4 de diseño quedaron resueltas arriba.)

## Principios

- Solo frontend: el backend no se toca; pytest debe seguir intacto (227+9) como
  verificación de no-regresión.
- Verde por fase: `npm run build` OK al cierre de cada fase; la app sigue usable
  aunque la fase siguiente no exista (aditivo → conexión → persistencia).
- Contrato HTTP explícito: paths con `/api/v1` explícito (convención de `api.js`).
- API caída ⇒ mensaje amable, nunca pantalla rota ni typing infinito.
- Cero dependencias nuevas, cero env vars nuevas.
- El mock muere solo cuando el reemplazo funciona (fase 2, no antes).

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | ambos | Ninguno | 5m | _(sin commit)_ |
| 1 | `api.js`: endpoints de conversación + timeout | frontend | Aditivo | 15m | `feat(front): add conversation endpoints to api client` |
| 2 | `useChat` conectado al orquestador real | frontend | Alto (muere el mock) | 30m | `feat(front): connect chat to llm orchestrator` |
| 3 | Sesión persistente: localStorage + rehidratación | frontend | Medio | 20m | `feat(front): persist chat session across reloads` |

Total: ~70m. (La verificación e2e manual de la Fase 2/3 consume cuota real de Gemini
— hacerla una vez por fase, no en loop.)

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: ambos
**Objetivo**: punto de partida verde y entorno listo para el e2e manual.
**Archivos afectados**: ninguno.
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Backend desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` → línea base
   esperada 227 passed + 9 skipped.
2. Frontend desde `frontend/`: `npm run build` → OK.
3. Confirmar que `backend/.env` tiene `GEMINI_API_KEY` (necesaria para el e2e manual
   de las fases 2-3) y que `frontend/.env` apunta `VITE_API_URL=http://localhost:8000`.

**Pruebas / verificación**: las de arriba.
**Riesgos**: cuota free tier de Gemini (20 req/día/modelo) — el e2e manual gasta ~4-6
requests por corrida; si la key del día está agotada, el flujo responde el fallback
del cliente Gemini (el chat igual "funciona", pero sin inteligencia — anotarlo al
verificar).

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit)_

---

## Fase 1 — `api.js`: endpoints de conversación + timeout

**Proyecto**: frontend
**Objetivo**: el cliente HTTP sabe hablar con el recurso `conversations` y deja de
poder colgarse indefinidamente. Aditivo puro: nadie lo consume aún (el mock sigue vivo).
**Archivos afectados**:
- [api.js](frontend/src/shared/services/api.js)

**Impacto en contrato API (front↔back)**: No (consume rutas que ya existen; el backend
no ve nada distinto).
**Acciones**:
1. Agregar timeout a `request()` con `AbortController` (60 s por defecto,
   sobreescribible por llamada); al abortar, lanzar un error distinguible
   (p. ej. `Error('timeout')`).
2. Exportar tres funciones nuevas siguiendo el patrón de `getHealth()`:
   - `createConversation()` → `POST /api/v1/conversations` con body `{}`;
   - `getConversation(sessionId)` → `GET /api/v1/conversations/{sessionId}`;
   - `postMessage(sessionId, content)` → `POST /api/v1/conversations/{sessionId}/message`
     con body `{ content }`.
3. Que el error HTTP conserve el status de forma consultable (p. ej. propiedad
   `status` en el Error) — la Fase 3 necesita distinguir 404 de otros fallos.

**Pruebas / verificación**: `npm run build` OK. Manual rápido: con backend levantado,
desde la consola del navegador (o un `curl` equivalente) crear conversación y ver el
201 con `session_id`.
**Riesgos**: ninguno (aditivo, sin consumidores).

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `feat(front): add conversation endpoints to api client`

---

## Fase 2 — `useChat` conectado al orquestador real

**Proyecto**: frontend
**Objetivo**: muere el mock; el chat conversa con el LLM real de punta a punta.
**Archivos afectados**:
- [useChat.js](frontend/src/features/chat/composables/useChat.js) — reescritura interna
  (el contrato `{ messages, isTyping, sendMessage }` hacia `ChatView` se conserva).
- [MessageBubble.vue](frontend/src/features/chat/components/MessageBubble.vue) — la
  hora se vuelve opcional (no renderizar `.time` si `message.timestamp` es null/undefined).

**Impacto en contrato API (front↔back)**: No cambia el contrato (consume lo existente).
Es la fase que enciende el consumo real del orquestador desde el navegador.
**Acciones**:
1. `useChat`: estado inicial = solo la burbuja local de bienvenida (rol bot, texto fijo
   tipo el saludo actual del mock; no viaja al backend).
2. `sendMessage(text)`: pinta el mensaje del usuario de inmediato (optimista),
   `isTyping = true`; si no hay sesión aún → `createConversation()` primero (creación
   perezosa, decisión 1); luego `postMessage(sessionId, text)`.
3. Con la respuesta: sincronizar `messages` desde `session.messages` (fuente de
   verdad, decisión 2) mapeando `role: 'assistant'→'bot'`, `'user'→'user'`,
   `content→text`; timestamps solo para mensajes nuevos de este cliente; conservar la
   burbuja de bienvenida local al frente; `isTyping = false`.
4. Error de red o timeout: `isTyping = false`, burbuja amable estilo bot (decisión 3),
   input habilitado para reintentar manualmente. El texto del usuario ya pintado se
   queda (no desaparece trabajo del usuario).
5. Eliminar `MOCK_BOT_REPLIES` y toda la maquinaria de mock.

**Pruebas / verificación**: `npm run build` OK. E2E manual (criterio 1 del vault):
levantar backend (`uvicorn`) + front (`npm run dev`) y desde el navegador correr el
flujo saludo → perfil → recomendación → cotización; verificar typing indicator durante
la latencia real del LLM. Caso negativo: bajar el backend y mandar un mensaje →
burbuja de error amable, la UI no se rompe y el input queda usable.
**Riesgos**: cuota Gemini del día agotada ⇒ el orquestador responde el fallback (la
conexión igual queda verificada — el guion inteligente se re-verifica cuando haya
cuota); latencia real de 10-30 s por turno con tools ⇒ es el comportamiento esperado,
el typing indicator lo cubre.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 3 sin aprobación del usuario.
**Commit sugerido**: `feat(front): connect chat to llm orchestrator`

---

## Fase 3 — Sesión persistente: localStorage + rehidratación

**Proyecto**: frontend
**Objetivo**: recargar la página conserva la conversación (criterio 2 del vault);
backend reiniciado no rompe el chat.
**Archivos afectados**:
- [useChat.js](frontend/src/features/chat/composables/useChat.js)

**Impacto en contrato API (front↔back)**: No (usa `GET /api/v1/conversations/{id}` ya
existente).
**Acciones**:
1. Al obtener `session_id` (creación perezosa de la Fase 2), guardarlo en
   localStorage (clave `chat_session_id`).
2. Al inicializar `useChat`: si hay `session_id` guardado → `getConversation(id)` y
   rehidratar el historial (mapeo de la Fase 2; sin timestamps — la burbuja ya oculta
   la hora ausente); la burbuja de bienvenida local va al frente. Si el `GET` da 404 o
   falla → limpiar localStorage y arrancar limpio (sin burbuja de error: para el
   usuario es simplemente un chat nuevo).
3. Recuperación en caliente (decisión 4): si `postMessage` devuelve 404 (backend
   reiniciado a mitad de conversación), limpiar la sesión, crear una nueva y reenviar
   ese mensaje una única vez; si vuelve a fallar, burbuja de error amable.

**Pruebas / verificación**: `npm run build` OK. Manual: conversar 2-3 turnos → F5 →
el historial sigue (criterio 2 ✓); borrar localStorage → F5 → chat nuevo con saludo;
reiniciar el backend a mitad de conversación → el siguiente mensaje crea sesión nueva
sin pantalla rota (la conversación previa se pierde hasta que C3 exista — esperado y
anotado). Caso negativo: API caída al recargar → chat nuevo utilizable, sin errores en
consola que rompan el render.
**Riesgos**: hasta que C3 (Postgres) exista, "conservar al recargar" depende de que el
backend no se haya reiniciado — limitación conocida del vault, no de este plan.

🛑 **CHECKPOINT** — fin del plan.
**Commit sugerido**: `feat(front): persist chat session across reloads`

---

## Deuda / fuera de alcance (anotada para el vault)

- **C3 pendiente**: la persistencia real (sobrevivir redeploys) llega con Postgres;
  este plan deja el front listo para beneficiarse sin cambios.
- **D3** (tarjetas de recomendación/cotización con `session.recommendation` y
  `session.quote`) y **D5** (nota de voz) quedan desbloqueadas por este plan.
- El texto de bienvenida y los microtextos de error se pulen en H4 (guiones del demo).
- `next_action` y `state` del `ConversationResponse` no se usan aún en la UI (los
  usará D3/D4).
