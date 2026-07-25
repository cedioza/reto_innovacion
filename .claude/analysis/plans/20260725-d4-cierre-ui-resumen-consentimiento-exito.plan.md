# Plan — D4: Cierre en la UI: resumen, consentimiento y éxito · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-25 · **Tipo**: plan de implementación por fases.
> **Base**: [20260725-d3-tarjetas-recomendacion-cotizacion-comparador.plan.md](.claude/analysis/plans/20260725-d3-tarjetas-recomendacion-cotizacion-comparador.plan.md)
> (patrón de mensajes tipados `type`/`payload` + tarjetas en `ChatView`) y
> [20260725-e1-handoff-correo-aseguradora-simulada.plan.md](.claude/analysis/plans/20260725-e1-handoff-correo-aseguradora-simulada.plan.md)
> (consent dispara correo real; `ConsentRequest.email` opcional pensado para D4).
> Tarea del vault: `07 - Tareas/Feature D - Chat web/D4 - Cierre en la UI resumen consentimiento y exito.md`
> (depende de **D3 ✅ y E1 ✅**, ambas ya en master; **bloquea H5**).
> Decisión de negocio: DEC-006 (cierre 100% automático vía handoff; **prohibido
> cualquier "te contactaremos"** — decisión del equipo 2026-07-24).
> **Proyectos afectados**: ambos (backend primero: mensajes tipados y textos;
> frontend después: tarjetas que los consumen).
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

El arco del demo termina **en pantalla**: tarjeta de resumen de la solicitud →
consentimiento explícito (checkbox con texto claro Ley 1581 + correo del cliente) →
tarjeta de éxito **"¡Listo! Tu solicitud va en camino: revisa tu correo para
finalizar con la aseguradora"** — 100% automático. Ningún texto del cierre (UI,
canal WhatsApp/Telegram, ni orquestador LLM) menciona contacto humano.

Criterios de aceptación del vault:
1. No se puede cerrar sin marcar el consentimiento (el backend ya lo valida:
   [conversation.py:170-171](backend/app/services/conversation.py#L170-L171)).
2. Tras confirmar, el correo del handoff (E1) llega de verdad al correo declarado
   en la conversación.
3. Ningún texto del cierre menciona contacto humano.

## Contexto / hallazgos del análisis

**Todo el backend del cierre ya existe (E1 en master) — D4 es sobre todo UI + textos:**

- `POST /api/v1/conversations/{id}/consent` acepta `consent_given` + `email`
  opcional ([conversations.py:54-61](backend/app/api/routes/conversations.py#L54-L61),
  [ConsentRequest](backend/app/schemas/conversation.py#L46-L48)) y devuelve
  `ConsentedApplication` (con `email`, `handoff_token`, `insurer_name`).
- [ConsentService.capture()](backend/app/services/consent.py#L32-L102) genera token +
  aseguradora y **envía el correo real** (best-effort) si hay `email` → el criterio 2
  se cumple con solo mandar `email` en el body desde la tarjeta.
- La máquina de estados estructurada: `QUOTE_READY` → `POST /accept` →
  `AWAITING_CONSENT` → `POST /consent` → `READY_FOR_PAYMENT`
  ([conversation.py:131-187](backend/app/services/conversation.py#L131-L187)).
  El front hoy **no consume** `/accept` ni `/consent`
  ([api.js](frontend/src/shared/services/api.js) solo tiene create/get/message/adjustments).
- Flujo LLM paralelo: `cerrar_venta` (consentimiento + email conversacionales,
  [agent_tools.py:301-349](backend/app/services/agent_tools.py#L301-L349)) captura
  directo y `_sync_ctx_to_session` deja `session.application` y `READY_FOR_PAYMENT`
  ([orchestrator.py:194-196](backend/app/services/orchestrator.py#L194-L196)).
  **Ambos caminos siguen válidos**; D4 agrega el camino visual determinista.

**Patrón de tarjetas D3 listo para extender:**

- Backend: `_append_card_messages` emite `Message(type="recommendation"|"quote"|"comparison", payload=...)`
  ([orchestrator.py:436-501](backend/app/services/orchestrator.py#L436-L501));
  `apply_adjustments` hace lo mismo por REST
  ([conversation.py:235-254](backend/app/services/conversation.py#L235-L254)).
- Frontend: `componentFor(message)` mapea tipo → tarjeta con fallback SIEMPRE a
  `MessageBubble` ([ChatView.vue:17-23](frontend/src/features/chat/ChatView.vue#L17-L23));
  `useChat.syncMessagesFromSession` reconstruye desde `session.messages`
  ([useChat.js:41-59](frontend/src/features/chat/composables/useChat.js#L41-L59)) —
  por eso las tarjetas nuevas deben nacer **en el backend como mensajes tipados**:
  así sobreviven al reload/rehidratación gratis.

**Los textos con contacto humano (criterio 3) — inventario exacto:**

- [channel_handler.py:52](backend/app/services/channel_handler.py#L52) — `DONE_TEXT`:
  "Pronto te contactaremos para coordinar el pago." → **único** "contactaremos" del
  backend (verificado por grep). Ningún test lo fija (verificado: solo
  `test_shared_conversation_state.py` toca el handler y no asserta estos textos).
- [channel_handler.py:68-71](backend/app/services/channel_handler.py#L68-L71) —
  `READY_TEXT`: "Si tenés dudas, contactanos." → también huele a contacto humano;
  se reescribe apuntando al correo.
- El `SYSTEM_PROMPT` del orquestador no promete contacto humano, pero tampoco
  instruye qué decir tras cerrar: se refuerza la regla 4
  ([orchestrator.py:70-73](backend/app/services/orchestrator.py#L70-L73)) para que el
  cierre diga "revisa tu correo" y **nunca** prometa contacto humano.

**Decisiones resueltas en el análisis:**

1. **Las tarjetas nacen en el backend como mensajes tipados** (patrón D3), no como
   estado local del front: `type="consent"` al pasar a `AWAITING_CONSENT` y
   `type="application"` al cerrar. Sobreviven reload (rehidratación ya existente) y
   sirven igual al camino estructurado y al LLM.
2. **La tarjeta de éxito se emite en los DOS caminos de cierre**: en
   `ConversationService.submit_consent` (camino tarjeta) y en
   `_append_card_messages` cuando `cerrar_venta_result` no es `None` (camino LLM).
   Mismo shape de payload, una sola tarjeta de front.
3. **El correo se pide en la tarjeta de consentimiento** (input email + checkbox):
   es el "correo declarado en la conversación" del criterio 2. El backend gana
   validación de formato (misma regex `^\S+@\S+\.\S+$` de
   [agent_tools.py:331](backend/app/services/agent_tools.py#L331)) en
   `submit_consent`: email presente pero inválido → `ValueError` → 400 (ruta
   negativa nueva). `email=None` sigue permitido (canal WhatsApp no lo captura).
4. **Entrada al flujo visual**: `QuoteCard` gana botón "Me interesa, continuar" →
   `POST /accept` → la sesión vuelve con la tarjeta de consentimiento. Demo
   determinista sin gastar cuota LLM (clave con las keys free tier). El camino
   conversacional (decirle al bot "acepto") sigue funcionando igual.
5. **Texto de éxito del canal (WhatsApp/Telegram)**: ese flujo NO captura email, así
   que su `DONE_TEXT` no puede prometer "revisa tu correo". Queda un cierre
   automático sin promesa de correo ni de contacto: "✅ ¡Listo! Tu solicitud quedó
   registrada y lista para pago. Gracias por confiar en Colsubsidio 🎉". El texto
   literal del vault ("revisa tu correo...") va donde sí hay correo: la tarjeta de
   éxito de la UI y el cierre del LLM (que exige email por construcción).
6. **Payload de la tarjeta de éxito mínimo**: `product_name`, `monthly_premium`,
   `currency`, `insurer_name`, `email`, `consent_timestamp`. El `handoff_token` NO
   viaja en la tarjeta (la página `/aseguradora/{token}` es E2; el link le llega al
   cliente por correo — la UI no lo necesita y no se filtra en pantalla).

## Decisiones pendientes (bloqueantes)

(ninguna — el texto del canal sin email queda resuelto arriba con justificación; si
el equipo quiere capturar email también por WhatsApp, es una tarea de canal aparte,
no bloquea D4.)

## Principios

- Backend primero (fase 1), frontend consume después (fase 2) — el contrato nuevo
  (tipos de mensaje `consent`/`application`) existe antes de que el front lo pinte.
- Contrato aditivo: tipos de mensaje nuevos con fallback a `MessageBubble` en el
  front viejo; endpoints existentes no cambian de firma/status; `email` inválido →
  400 es la única validación nueva (ruta negativa, nunca 500).
- Las cifras de las tarjetas salen del motor tal cual (regla D3: el front solo
  formatea, jamás calcula).
- Verde por fase: pytest backend / `npm run build` frontend; API caída → burbuja de
  error, nunca pantalla rota (patrón `ERROR_TEXT` existente).
- Cero dependencias nuevas, cero env vars nuevas. TDD-light en fase backend.

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | ambos | Ninguno | 5m | _(sin commit)_ |
| 1 | Mensajes tipados de cierre + textos 100% automáticos | backend | Medio (contrato aditivo) | 40m | `feat(back): emit consent and success cards, drop human contact` |
| 2 | ConsentCard + SuccessCard + flujo de cierre en el chat | frontend | Medio | 45m | `feat(front): close the chat with consent and success cards` |

Total: ~90m. (H5 —guion del demo— queda desbloqueada al terminar; E2 —página del
link— es independiente y puede correr en paralelo.)

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: ambos
**Objetivo**: punto de partida verde.
**Archivos afectados**: ninguno.
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Backend desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` → línea base
   (241 passed + 9 skipped en master hoy; **251+9 si la rama B1
   `plan/164736-b1-catalogo-multiproducto-json` ya se mergeó** — registrar la que
   aparezca).
2. Frontend desde `frontend/`: `npm run build` → OK.
3. Registrar que `POST /{id}/consent` con `email` ya dispara correo (E1 en master —
   solo confirmar que `app/services/handoff.py` y `resend_client.py` existen).

**Pruebas / verificación**: las de arriba.
**Riesgos**: ninguno.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit)_

---

## Fase 1 — Mensajes tipados de cierre + textos 100% automáticos

**Proyecto**: backend
**Objetivo**: la sesión emite tarjetas de consentimiento y de éxito como mensajes
tipados (en ambos caminos de cierre), el email se valida, y ningún texto del backend
menciona contacto humano.
**Archivos afectados**:
- [conversation.py (service)](backend/app/services/conversation.py):
  - `accept_quote` — además del texto actual, append de
    `Message(role="assistant", type="consent", content="📝 Consentimiento: confirma para dejar tu solicitud lista", payload={"product_id", "product_name", "monthly_premium", "annual_premium", "currency", "coverage_details"})`
    (todo desde `session.recommendation`/`session.quote` — resumen para la tarjeta).
  - `submit_consent` — validación de email: presente pero sin formato válido
    (regex `^\S+@\S+\.\S+$`) → `ValueError("Email inválido")` → 400 en la ruta
    (antes de llamar a `capture`); tras `capture`, append del texto de éxito
    ("¡Listo! Tu solicitud va en camino: revisa tu correo para finalizar con la
    aseguradora 🎉" — variante sin promesa de correo si `email is None`) + append de
    `Message(type="application", content="🎉 Solicitud lista — pendiente de pago", payload={"product_name", "monthly_premium", "currency", "insurer_name", "email", "consent_timestamp"})`
    y `session.next_action = "Revisa tu correo para finalizar con la aseguradora"`.
    (El `handoff_token` NO va en el payload — decisión 6.)
- [orchestrator.py](backend/app/services/orchestrator.py):
  - `_append_card_messages` gana el parámetro `cerrar_venta_result` y emite la
    MISMA tarjeta `application` (mismo shape; `insurer_name`/`email`/`consent_timestamp`
    salen del propio resultado de la tool) después del texto del turno.
  - Regla 4 del `SYSTEM_PROMPT`
    ([orchestrator.py:70-73](backend/app/services/orchestrator.py#L70-L73)) ampliada:
    tras el cierre exitoso dile al cliente que revise su correo para finalizar con
    la aseguradora; **nunca** digas que lo contactará una persona ("te
    contactaremos", "un asesor te llamará" están prohibidos — el cierre es 100%
    automático).
- [channel_handler.py](backend/app/services/channel_handler.py) —
  `DONE_TEXT` → "✅ ¡Listo! Tu solicitud de Hogar Estándar quedó registrada y lista
  para pago. Gracias por confiar en Colsubsidio 🎉" (sin "contactaremos");
  `READY_TEXT` → "Tu solicitud ya está lista para pago. Tu comprobante queda
  registrado en el sistema." (sin "contactanos").
- Tests nuevos (`tests/test_closing_cards.py`):
  - `accept_quote` → el último mensaje es `type="consent"` con
    `product_name`/`monthly_premium` correctos del motor;
  - `submit_consent` con email válido → la sesión gana texto de éxito + mensaje
    `type="application"` con `insurer_name`/`email`, y el texto NO contiene
    "contactaremos" ni "contactanos";
  - `submit_consent` sin email (canal) → cierra igual, tarjeta con `email: None`,
    texto de éxito sin promesa de correo;
  - **ruta negativa**: `POST /{id}/consent` con `email="no-es-correo"` → 400 (y no
    se crea solicitud ni se envía correo — `resend_client` mockeado);
  - cierre por LLM guionizado (patrón de
    [test_handoff_flow.py](backend/tests/test_handoff_flow.py)): `cerrar_venta` OK →
    la sesión contiene la tarjeta `application`;
  - textos del canal: la respuesta de cierre del `ChannelHandler` no contiene
    "contactaremos"/"contactanos".
- Tests existentes a revisar (ajuste de expectativa, no debilitamiento): los que
  cierran por LLM guionizado e inspeccionan `messages[-1]`
  ([test_handoff_flow.py](backend/tests/test_handoff_flow.py),
  [test_guardrails.py](backend/tests/test_guardrails.py) ya filtra por tipo texto) —
  con la tarjeta `application` al final del turno, cambiar `messages[-1]` por el
  último mensaje de `type == "text"` donde aplique.

**Impacto en contrato API (front↔back)**: **Sí — aditivo.** `session.messages` gana
dos tipos nuevos (`consent`, `application`) con sus payloads; `POST /{id}/consent`
devuelve 400 ante email con formato inválido (antes lo aceptaba en silencio). El
front viejo no se rompe (tipos desconocidos caen a `MessageBubble`). **Quién
actualiza el otro lado**: la Fase 2 de este mismo plan.
**Acciones**:
1. TDD-light: `tests/test_closing_cards.py` primero (rojo por la razón correcta).
2. Service → orquestador → channel handler → prompt.
3. Suite completa verde (ajustes de expectativa incluidos).

**Pruebas / verificación**: pytest completo verde; grep final: `contactaremos` y
`contactanos` con cero matches en `backend/app/`.
**Riesgos**: tests guionizados que asuman `messages[-1]` textual tras el cierre
(inventariados arriba — ajuste puntual); el texto de éxito con/sin email tiene dos
variantes — cubierto por tests dedicados.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `feat(back): emit consent and success cards, drop human contact`

---

## Fase 2 — ConsentCard + SuccessCard + flujo de cierre en el chat

**Proyecto**: frontend
**Objetivo**: el usuario cierra el arco completo en pantalla: cotización → "Me
interesa" → tarjeta de resumen + checkbox Ley 1581 + correo → confirmación → tarjeta
de éxito 🎉. Todo con etiqueta de simulación y sin campos de pago (regla E1).
**Archivos afectados**:
- [api.js](frontend/src/shared/services/api.js) — `postAccept(sessionId)` →
  `POST /api/v1/conversations/{id}/accept`; `postConsent(sessionId, email)` →
  `POST /api/v1/conversations/{id}/consent` con `{consent_given: true, email}`.
- [useChat.js](frontend/src/features/chat/composables/useChat.js) —
  `acceptQuote()` (llama `postAccept` y sincroniza con `syncMessagesFromSession`) y
  `submitConsent(email)` (llama `postConsent`; como devuelve `ConsentedApplication`
  y no la sesión, re-sincroniza con `getConversation(sessionId)`); flag
  `isClosing` para deshabilitar botones mientras corre; errores → burbuja
  `ERROR_TEXT` existente (API caída → el chat no revienta).
- `frontend/src/features/chat/components/ConsentCard.vue` (nuevo) — resumen de la
  solicitud desde `message.payload` (producto, prima mensual formateada es-CO,
  coberturas), input de correo (type email, requerido), checkbox con texto claro:
  "Autorizo el tratamiento de mis datos personales (Ley 1581 de 2012) y confirmo
  que entiendo coberturas y exclusiones para dejar mi solicitud lista para pago.",
  nota visible "Entorno de demostración — no se realizará ningún cobro." y botón
  "Confirmar solicitud" deshabilitado hasta checkbox + email con formato válido
  (misma regex del backend). Emite `confirm(email)`. Sin campos de tarjeta, ni
  reales ni falsos (regla E1). Estilos calcados de
  [QuoteCard.vue](frontend/src/features/chat/components/QuoteCard.vue).
- `frontend/src/features/chat/components/SuccessCard.vue` (nuevo) — "🎉 ¡Ya quedaste
  asegurado! (pendiente de pago)" + "Tu solicitud va en camino: revisa tu correo
  **{email}** para finalizar con **{insurer_name}**" + qué llega al correo
  (comprobante con producto y prima + link de la aseguradora) + etiqueta
  "(simulación — entorno de demostración)". Si `payload.email` es null, variante
  sin la línea de correo.
- [QuoteCard.vue](frontend/src/features/chat/components/QuoteCard.vue) — botón
  primario "Me interesa, continuar" (emite `accept`) junto al secundario existente
  "Ajustar coberturas".
- [ChatView.vue](frontend/src/features/chat/ChatView.vue) — `componentFor`: mapear
  `'consent'` → `ConsentCard` y `'application'` → `SuccessCard`; `extraPropsFor`:
  `quote` gana `onAccept: acceptQuote`; `consent` recibe
  `{ busy: isClosing, onConfirm: submitConsent }`. Tras `READY_FOR_PAYMENT`, la
  ConsentCard previa queda inerte (prop `disabled` si `session.state` ya cerró — o
  el 400 del backend cae a burbuja de error, nunca pantalla rota).
**Impacto en contrato API (front↔back)**: No — consume lo que la Fase 1 ya expone;
ninguna env var nueva.
**Acciones**:
1. `api.js` + `useChat` (frontend).
2. Tarjetas nuevas + botón en `QuoteCard` + wiring en `ChatView` (frontend).
3. `npm run build` verde + prueba manual del arco completo.

**Pruebas / verificación**: `npm run build` OK; manual con `python dev.py`: sembrar
por REST (`POST /profile` con perfil válido — sin gastar LLM) → la QuoteCard muestra
"Me interesa" → click → aparece ConsentCard → botón deshabilitado sin checkbox o con
email malo (criterio 1 en UI) → confirmar con un correo real (buzón Resend) → aparece
SuccessCard y **el correo llega** (criterio 2) → reload de la página → las tarjetas
de cierre siguen (rehidratación); negativo: backend caído al confirmar → burbuja de
error y el input sigue usable; email inválido forzado por consola → 400 → burbuja.
**Riesgos**: doble cierre (usuario confirma la tarjeta después de cerrar por chat
LLM) → el backend responde 400 y el front lo muestra como burbuja de error — feo
pero no roto; mitigación barata incluida (tarjeta inerte si el estado ya es
`ready_for_payment`). Resend free tier solo entrega al buzón del dueño de la cuenta
(pendiente operativo heredado de E1 — para la demo usar ese buzón).

🛑 **CHECKPOINT** — fin del plan.
**Commit sugerido**: `feat(front): close the chat with consent and success cards`

---

## Deuda / fuera de alcance (anotada para el vault)

- **E2**: página `/aseguradora/{token}` — el link del correo apunta ahí; hasta que
  exista, el botón del correo lleva a una ruta sin registrar (el correo sale igual).
- **Canal WhatsApp/Telegram**: no captura email → su cierre no promete correo.
  Capturar email por canal sería una mejora del `channel_handler`, tarea aparte.
- **H5**: el guion del demo puede apoyarse en el camino determinista por tarjetas
  (cero cuota LLM) — anotarlo al escribirlo.
- El texto legal del checkbox es copy de MVP (Ley 1581 de 2012 mencionada
  explícitamente); si el equipo tiene el wording jurídico exacto, es un cambio de
  string en `ConsentCard.vue`.
