# Plan — F5: Adaptador de canal Telegram · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-26 · **Tipo**: plan de implementación por fases (micro-plan).
> **Base**: [20260726-f1-webhooks-conectados-orquestador.plan.md](.claude/analysis/plans/20260726-f1-webhooks-conectados-orquestador.plan.md)
> (mergeado a master `25f5a82`: contrato `channels/base.py`, `channel_gateway.handle`
> canal-agnóstico con fallback regex, y `MetaWhatsAppAdapter` como referencia).
> Tarea del brain: **F5 — Adaptador de canal Telegram** (depende de F1 ✔; plan C de
> canal según "Canal y costos WhatsApp"; recortable, pero vale oro como demo de
> arquitectura: "mírenlo en Telegram sin cambiar una línea del agente").
> **Proyectos afectados**: backend.
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

El webhook de Telegram (`POST /webhooks/telegram`, ya implementado y con tests) se
enchufa al contrato de adaptador de F1 y pasa los mensajes al orquestador LLM. Es la
demostración en vivo del argumento "adaptador delgado": un canal que no es WhatsApp,
el mismo agente, **cero cambios en el core** (verificable en el diff — criterio 3).

## Contexto / hallazgos del análisis

- **El contrato F1 ya está en master** y este es su primer cliente nuevo:
  [channels/base.py](backend/app/services/channels/base.py) (`InboundMessage`,
  `split_text`, `markdown_bold_to_whatsapp`),
  [channel_gateway.handle](backend/app/services/channel_gateway.py) (sesión por
  `sesiones_canal` con el canal en la clave, turno LLM, fallback regex sin
  `GEMINI_API_KEY`) y [meta_whatsapp.py](backend/app/services/channels/meta_whatsapp.py)
  como plantilla exacta del patrón.
- **El webhook Telegram sigue en el camino legacy**:
  [webhooks.py:130-142](backend/app/api/routes/webhooks.py#L130-L142) — parsing
  inline (`message.chat.id` con fallback a `from.id`, `text`) →
  `_handler.handle_incoming("telegram", ...)` → `send_telegram_message`. La
  validación del secret (`X-Telegram-Bot-Api-Secret-Token` → 401,
  [webhooks.py:145-148 aprox](backend/api/routes/webhooks.py)) vive ANTES del try y
  no se toca. Ojo: el handler corre síncrono dentro del `async def` — con el turno
  LLM debe pasar a `run_in_threadpool` (como ya hace el camino Meta post-F1).
- **Formato Telegram**: [telegram_client.send_telegram_message](backend/app/services/telegram_client.py#L8-L21)
  envía con `parse_mode: "Markdown"` (Markdown legacy de Telegram: negrita con UN
  asterisco `*x*`, igual que WhatsApp) — así que `markdown_bold_to_whatsapp` del
  contrato sirve tal cual para convertir el `**x**` del LLM. Límite de mensaje de
  Telegram: 4096 chars (mismo `split_text(4096)`).
  **Riesgo propio de Telegram**: con `parse_mode=Markdown`, entidades sin cerrar
  (un `*` suelto en el texto del LLM) hacen que la API rechace el mensaje con 400 →
  `send_telegram_message` devuelve False y el usuario no recibe NADA. Mitigación
  barata: parámetro opcional `parse_mode` en el cliente y reintento del trozo en
  texto plano si el envío formateado falla.
- **Sesión por chat_id**: `handle("telegram", str(chat_id), texto)` — el gateway ya
  persiste con el canal en la PK (`sesiones_canal`), así que un mismo humano por
  WhatsApp y Telegram son sesiones distintas (decisión explícita del MVP en la
  tarea).
- **Tests existentes a adaptar (sin debilitar)**:
  [test_telegram_webhook.py](backend/tests/test_telegram_webhook.py) monkeypatchea
  `webhooks._handler.handle_incoming` y `webhooks.send_telegram_message` — tras el
  re-cableo, el mock cambia a `webhooks.channel_gateway.handle` y al deliver del
  adaptador; los asserts de secret válido/faltante/incorrecto → 200/401/401 quedan
  IDÉNTICOS (criterio 2). `test_telegram_webhook_setup.py` (endpoint `/telegram/set`)
  no se toca.
- **Smoke real** (criterio 1): mensaje al bot de Telegram → conversación LLM
  completa. Requiere `TELEGRAM_BOT_TOKEN` + `BACKEND_PUBLIC_URL` (webhook
  registrado) + key Gemini — verificación manual, la de código queda mockeada.

## Decisiones pendientes (bloqueantes)

(ninguna — resueltas en el análisis:)

- **Reutilizar `markdown_bold_to_whatsapp` para Telegram** (el Markdown legacy de
  Telegram usa la misma negrita de un asterisco). Si algún día se pasa a MarkdownV2,
  será un helper propio — fuera de alcance.
- **Fallback de formato**: si el envío con `parse_mode=Markdown` falla, el adaptador
  reintenta ese trozo en texto plano (`parse_mode=None`) — mejor sin negritas que
  sin respuesta. Cambio aditivo y retrocompatible en `send_telegram_message`.
- **`chat_id` como string** en el gateway (la PK de `sesiones_canal` es string); el
  `deliver` envía con el mismo valor (la API de Telegram acepta int o string).

## Principios

- Verde por fase; tests de conversación con LLM mockeado (cero cuota).
- **El core no se toca**: ni `channel_gateway`, ni `channels/base`, ni orquestador,
  ni adaptador Meta — el diff debe ser solo: adaptador nuevo + bloque Telegram del
  router + cliente (param opcional) + tests (criterio 3 verificable).
- Contrato HTTP externo intacto: misma ruta, mismo secret → 401, mismo
  `{"status": "ok"}`.
- Cero dependencias nuevas, cero env vars nuevas.

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | backend | Ninguno | 5m | _(sin commit)_ |
| 1 | Adaptador Telegram enchufado al gateway | backend | Aditivo | 35m | `feat(channels): plug telegram adapter into gateway` |

Total estimado: ~40m (estimación del brain: 1h — F1 hizo el trabajo pesado).

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: backend
**Objetivo**: baseline verde post-F1 y confirmación de los puntos de enganche.
**Archivos afectados**: ninguno (solo lectura).
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` (anotar baseline —
   master viene de F1+G4+G5+A6; ~573 passed, 11 skipped).
2. Releer `test_telegram_webhook.py` completo: qué mockea cada test y qué asserts
   de 401 deben sobrevivir idénticos.
3. Confirmar en `meta_whatsapp.py` + `test_meta_channel_adapter.py` el patrón de
   estructura que los tests de F1 fijaron (import de la función de envío como
   símbolo del módulo del adaptador; gateway importado como módulo en webhooks) —
   F5 replica ese patrón para poder monkeypatchear igual.
**Pruebas / verificación**: suite corrida y baseline anotado.
**Riesgos**: ninguno.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit — fase de solo lectura)_

---

## Fase 1 — Adaptador Telegram enchufado al gateway

**Proyecto**: backend
**Objetivo**: Telegram habla con el agente LLM vía el contrato de F1; el secret
sigue rechazando con 401; el core queda intacto (los 3 criterios de F5).
**Archivos afectados**:
`backend/app/services/channels/telegram.py` (nuevo) ·
[telegram_client.py](backend/app/services/telegram_client.py) (param opcional
`parse_mode`) ·
[webhooks.py](backend/app/api/routes/webhooks.py) (solo el bloque del POST
`/telegram`) ·
`backend/tests/test_telegram_channel_adapter.py` (nuevo) ·
[test_telegram_webhook.py](backend/tests/test_telegram_webhook.py) (re-apuntar
mocks, asserts idénticos)
**Impacto en contrato API (front↔back)**: No para el frontend web; el contrato
EXTERNO del webhook Telegram (ruta, secret→401, 200 siempre) se conserva — cambia
el motor de respuesta (keywords → LLM vía gateway).
**Acciones**:
1. `telegram_client.py`: `send_telegram_message(chat_id, text, parse_mode="Markdown")`
   — el default conserva el comportamiento actual; `parse_mode=None` omite la clave
   del payload (texto plano). Nada más cambia.
2. `channels/telegram.py` (nuevo) — `TelegramAdapter` contra el contrato (docstring
   español: plan C de canal; Markdown legacy comparte la negrita `*x*` con
   WhatsApp):
   - `channel = "telegram"`.
   - `parse_incoming(payload) -> InboundMessage | None`: el parsing exacto del
     bloque actual (`message.chat.id` con fallback a `message.from.id`, `text`);
     sin chat_id o sin texto → None, jamás excepción.
     `InboundMessage("telegram", str(chat_id), text)`.
   - `deliver(user_ref, text) -> bool`: `markdown_bold_to_whatsapp` +
     `split_text(text, 4096)` + `send_telegram_message` por trozo EN ORDEN; si un
     trozo falla con Markdown, reintenta ESE trozo con `parse_mode=None`; si
     también falla → False y corta; todo OK → True; vacío → True.
   - Import como símbolo: `from app.services.telegram_client import
     send_telegram_message` (patrón F1 para monkeypatch).
3. `webhooks.py` — SOLO el cuerpo del try del POST `/telegram`: instancia
   módulo-level `_telegram_adapter = TelegramAdapter()`;
   `inbound = _telegram_adapter.parse_incoming(payload)` → None ⇒
   `{"status": "ok"}`; con mensaje ⇒ `run_in_threadpool(channel_gateway.handle,
   inbound.channel, inbound.user_ref, inbound.text)` →
   `run_in_threadpool(_telegram_adapter.deliver, inbound.user_ref, respuesta)`.
   La validación del secret (antes del try) y el `except → 200` quedan INTACTOS.
   Nada más del archivo cambia (Meta/YCloud intocados).
4. Tests (TDD-light, rojo primero) en `test_telegram_channel_adapter.py`:
   - `parse_incoming`: update real con texto → InboundMessage("telegram", chat_id
     str, texto); update con `from.id` y sin `chat.id` → usa from.id; sin texto /
     payload basura / `{}` → None sin excepción.
   - `deliver`: texto largo → trozos ≤4096 en orden; `**negrita**` → `*negrita*`;
     primer envío False con Markdown → reintento del MISMO trozo con
     `parse_mode=None` (espía graba los kwargs); reintento también False → False y
     corta; feliz → True.
   - Webhook por gateway (TestClient + `webhooks.channel_gateway.handle` mockeado):
     POST update válido → 200, `handle("telegram", chat_id, texto)` llamado y
     respuesta entregada; POST basura → 200 sin llamar handle; `handle` lanza →
     200.
   - **Criterio 3 en el diff**: assert de que `TelegramAdapter` NO está importado
     por `channel_gateway`/`channels/base` (el core no conoce el canal) — o
     simplemente se verifica en el checkpoint con `git diff --stat` (core ausente).
5. Re-apuntar los mocks de `test_telegram_webhook.py` (de `_handler.handle_incoming`
   a `channel_gateway.handle`; de `send_telegram_message` al deliver o al símbolo
   del adaptador) manteniendo IDÉNTICOS los asserts de secret 200/401/401
   (criterio 2).
6. README backend, sección Canales: marcar Telegram como enchufado al contrato
   (deuda restante: YCloud → F4).
**Pruebas / verificación**: pytest completo en verde. **Manual (criterio 1, anotar
como pendiente si no hay entorno)**: registrar webhook (`POST /webhooks/telegram/set`
con `BACKEND_PUBLIC_URL` público), escribirle al bot y conversar con el agente LLM;
verificar 401 con secret malo vía curl.
**Riesgos**: mensajes del LLM con Markdown desbalanceado → cubierto por el
reintento plano; latencia del turno LLM en el webhook → `run_in_threadpool` (mismo
patrón Meta); Telegram reintenta updates no confirmados → el 200 inmediato tras el
turno lo cubre igual que hoy (dedupe por `update_id` queda como follow-up anotado
en el README, análogo al de Meta).

🛑 **CHECKPOINT FINAL** — F5 cumple: smoke real pendiente de entorno (criterio 1),
secret 401 intacto (criterio 2), y el diff demuestra que el core no se tocó
(criterio 3 — el argumento de arquitectura en vivo para el pitch). Marcar F5 en el
brain.
**Commit sugerido**: `feat(channels): plug telegram adapter into gateway`
