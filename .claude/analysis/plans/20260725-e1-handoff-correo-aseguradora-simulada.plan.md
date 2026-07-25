# Plan — E1: Handoff por correo con link de aseguradora simulada · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-25 · **Tipo**: plan de implementación por fases.
> **Base**: [20260723-health-terceros-backend.plan.md](.claude/analysis/plans/20260723-health-terceros-backend.plan.md)
> (health check de Resend ya operativo),
> [20260725-a3-orquestador-conversacional-llm.plan.md](.claude/analysis/plans/20260725-a3-orquestador-conversacional-llm.plan.md)
> (tool `cerrar_venta` + `ConsentService`) y
> [20260725-d3-tarjetas-recomendacion-cotizacion-comparador.plan.md](.claude/analysis/plans/20260725-d3-tarjetas-recomendacion-cotizacion-comparador.plan.md)
> (mensajes tipados — patrón reutilizable a futuro para una tarjeta de cierre en D4).
> Tarea del vault: `07 - Tareas/Feature E - Cierre automatico/E1 - Handoff correo con link de aseguradora simulada.md`
> (sin dependencias; **bloquea D4, E2, E3, E4**). Decisión de negocio:
> DEC-006 (handoff a aseguradora vía link al correo, sin pasarela — ⚠️ marcada
> "pendiente de ratificar", ver Decisiones pendientes).
> **Proyectos afectados**: backend (solo backend; la página del link es E2, otra tarea).
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

Al capturar el consentimiento, el sistema envía **automáticamente** (Resend) un correo
al cliente con el resumen de su solicitud (producto, prima, razones) y el **link hacia
la "aseguradora" simulada** (`{FRONTEND_URL}/aseguradora/{token}`, página que construye
E2) — cero interacción humana. El bot **nunca cierra sin correo de destino**: la tool
`cerrar_venta` lo exige y el LLM lo pide en conversación. Un fallo de Resend **no rompe
el cierre**: la solicitud queda registrada y el error, logueado.

Criterios de aceptación del vault:
1. Consentimiento → correo real llega en <1 min con producto, prima y link.
2. Sin correo declarado, el bot lo pide antes del consentimiento.
3. Si Resend falla, el flujo del chat termina bien igual y el error queda logueado.

## Contexto / hallazgos del análisis

**Lo que ya existe:**

- [consent.py](backend/app/services/consent.py) — `ConsentService.capture()` es el
  **punto único de cierre**: lo llaman tanto la tool `cerrar_venta`
  ([agent_tools.py:361](backend/app/services/agent_tools.py#L361)) como el endpoint
  estructurado `POST /{id}/consent`
  ([conversation.py:170](backend/app/services/conversation.py#L170)). Disparar el
  correo aquí cubre ambos caminos con un solo cambio (paso sugerido del vault ✓).
- [integrations/resend.py](backend/app/services/integrations/resend.py) — health check
  activo que YA envía correos reales (`https://api.resend.com/emails`, remitente
  `onboarding@resend.dev`, key en `Settings`). Patrón httpx sin SDK listo para clonar
  como cliente de envío.
- `RESEND_API_KEY`/`RESEND_TEST_TO` ya en [config.py](backend/app/core/config.py#L17-L18)
  y [.env.example](backend/.env.example#L26-L30); `frontend_url` también en Settings →
  **cero env vars nuevas**.

**Lo que falta (los huecos que este plan cierra):**

- **No existe el correo del cliente en ninguna parte**: ni `ProfileData`, ni
  `ConsentedApplication` ([conversation.py:47-54](backend/app/schemas/conversation.py#L47-L54)),
  ni la declaración de `cerrar_venta`
  ([agent_tools.py:302-322](backend/app/services/agent_tools.py#L302-L322)) lo
  capturan. Nota de diseño: el email es **dato declarado por el cliente**, así que SÍ
  puede viajar por los args de la tool (la regla "el estado del funnel no viaja por el
  LLM" aplica a precios/perfil calculado, no a lo que el cliente dicta).
- **No existe token de handoff**: E2 espera `GET /api/v1/handoff/{token}` y una ruta
  de front `/aseguradora/{token}`. E1 debe generar el token al cerrar y guardarlo en
  la solicitud (E2 lo consumirá).
- **No existe envío de correo transaccional** (solo el health check).
- La regla 4 del [SYSTEM_PROMPT](backend/app/services/orchestrator.py#L70-L72) pide
  consentimiento pero no correo — hay que extenderla (refuerzo suave; el refuerzo
  duro es el error controlado de la tool, que obliga al LLM a pedirlo — regla 5).

**Restricción operativa de Resend (free tier) a tener presente:**

- Con el remitente `onboarding@resend.dev` (sin dominio verificado), Resend **solo
  entrega al correo del dueño de la cuenta**. Para el criterio 1 "probado con correos
  del equipo" hay dos salidas: verificar un dominio en Resend (ideal, si el equipo
  tiene uno) o demo con el buzón de la cuenta (`RESEND_TEST_TO`). El código queda
  agnóstico (remitente en constante, como el health check); es un pendiente operativo,
  no de código — anotado en riesgos.

**Decisiones resueltas en el análisis:**

1. **El disparo vive en `ConsentService.capture()`** — cubre chat y endpoint
   estructurado. El envío es *best-effort*: `try` alrededor, fallo → `logging.error`
   (sin API key en el mensaje) y la solicitud se persiste igual (criterio 3). Sin
   reintento automático en esta tarea (el log visible basta para el MVP; E3/E4
   pueden sumar cola si hace falta).
2. **Token de handoff = `secrets.token_urlsafe(32)`** persistido en la solicitud —
   sin firmas ni dependencias nuevas (no itsdangerous/jwt); E2 lo resolverá contra el
   repositorio. Expiración: ninguna (el jurado entra días después — nota de E2).
   Sobrevivir redeploys depende de C3 (misma deuda que todo lo persistido).
3. **`cerrar_venta` exige `email`**: se agrega a `parameters.required` de la
   declaración + validación de formato en el handler (regex simple) → sin email o
   inválido devuelve error controlado y el LLM lo pide (criterio 2 por construcción,
   no por prompt). El endpoint estructurado `POST /{id}/consent` acepta `email`
   **opcional** en el body (D4 lo mandará); sin email simplemente no se envía correo
   (no hay destino) y se loguea.
4. **Aseguradora simulada**: constante `INSURER_BY_PRODUCT` en el servicio de handoff
   (`hogar-estandar` → "Seguros Bolívar"), siempre etiquetada "(simulación)". El
   nombre viaja en la solicitud (`insurer_name`) para que chat, correo y página E2
   digan lo mismo (nota del vault). Ajustable en H4 sin tocar lógica.
5. **HTML inline sin plantillas nuevas** (sin jinja2): f-string en el servicio de
   handoff con producto, prima mensual/anual (cifras del motor tal cual), razones
   (label + evidence) y botón-link `{FRONTEND_URL}/aseguradora/{token}`. Es un
   hackathon: una función que retorna `(subject, html)` testeable.

## Decisiones pendientes (bloqueantes)

(ninguna — **DEC-006 confirmada por Carlos el 2026-07-25**: el cierre es
"comprobante + link a la aseguradora": el chat captura consentimiento, el correo
lleva el **comprobante de la solicitud** (producto, prima, coberturas, razones) y el
botón "Finalizar con la aseguradora" hacia la página de E2. La compra se consuma en
la página simulada, no en el chat — coherente con el mandato "hasta antes del pago".
Falta solo socializarlo con Cristian, no bloquea la ejecución.)

(la restricción de entrega de Resend NO bloquea el código — ver riesgos de Fase 2.)

## Principios

- Solo backend; la página del link es E2 (el link puede apuntar a una ruta de front
  que aún no existe — el correo sale igual y E2 la construye después).
- Cierre robusto: el correo es best-effort; la captura de consentimiento NUNCA falla
  por culpa de Resend (criterio 3 por diseño).
- El email es dato declarado → viaja por args de tool; precios/razones siguen
  saliendo solo del motor (el correo cita `quote`/`recommendation` de la solicitud).
- Contrato aditivo: `ConsentedApplication` gana campos opcionales; nada existente
  cambia de shape ni de status code.
- Secretos jamás en logs ni en tests; el cliente de Resend se mockea en la suite
  (cero correos reales en pytest).
- Cero dependencias nuevas, cero env vars nuevas. TDD-light por fase.

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | ambos | Ninguno | 5m | _(sin commit)_ |
| 1 | Cliente de envío Resend + constructor del correo de handoff | backend | Aditivo | 30m | `feat(back): add resend send client and handoff email builder` |
| 2 | Email en `cerrar_venta` + disparo del correo al capturar consentimiento | backend | Medio (contrato aditivo) | 35m | `feat(back): send handoff email on consent capture` |

Total: ~70m. (E2 —página del link—, D4 —tarjeta de cierre en UI— y E3/E4 quedan
desbloqueadas al terminar.)

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: ambos
**Objetivo**: punto de partida verde y Resend operativo.
**Archivos afectados**: ninguno.
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Backend desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` → línea base
   (241 passed + 9 skipped si D3 ya está en master; registrar la que aparezca).
2. Frontend desde `frontend/`: `npm run build` → OK (no se toca, pero queda el registro).
3. Resend vivo: levantar uvicorn y `POST /api/v1/health/integrations/resend` → `ok: true`
   (manda un correo real de prueba a `RESEND_TEST_TO`; confirma key válida y buzón).

**Pruebas / verificación**: las de arriba.
**Riesgos**: si el health de Resend falla, la Fase 2 no podrá verificarse en vivo —
resolver la key/buzón antes de ejecutar.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit)_

---

## Fase 1 — Cliente de envío Resend + constructor del correo de handoff

**Proyecto**: backend
**Objetivo**: piezas puras y testeables, sin tocar el flujo: enviar un correo
arbitrario vía Resend y construir el contenido del correo de handoff. Aditivo total.
**Archivos afectados**:
- `app/services/integrations/resend_client.py` (nuevo) — `send_email(to, subject,
  html) -> dict` con httpx (patrón de
  [resend.py](backend/app/services/integrations/resend.py): timeout 10s, remitente
  constante `RESEND_FROM = "onboarding@resend.dev"`, nunca lanza — devuelve
  `{"ok": bool, "id"|"error": ...}`, sin API key en errores; sin configurar →
  `{"ok": False, "error": "no configurado..."}`).
- `app/services/handoff.py` (nuevo) — servicio del handoff:
  - `INSURER_BY_PRODUCT = {"hogar-estandar": "Seguros Bolívar"}` + fallback genérico
    ("la aseguradora aliada").
  - `new_token() -> str` (`secrets.token_urlsafe(32)`).
  - `build_handoff_email(application, token) -> tuple[subject, html]` — HTML inline
    con formato de **comprobante de la solicitud** (asunto tipo "Comprobante de tu
    solicitud — Hogar Estándar"): nombre del producto, prima mensual y anual (tal
    cual del `quote`, formato COP con separador de miles), coberturas incluidas,
    razones de la recomendación (label + evidence), fecha del consentimiento,
    botón-link `{settings.frontend_url}/aseguradora/{token}` "Finalizar con
    [aseguradora]" y etiqueta visible "(simulación — entorno de demostración)".
- Tests nuevos (`tests/test_handoff.py`): builder — el HTML contiene producto, prima
  mensual y anual EXACTAS del quote, ≥2 razones, el link con el token y la etiqueta de
  simulación; token único por llamada y URL-safe; cliente — `send_email` con httpx
  mockeado (monkeypatch) devuelve ok con id / error controlado en 4xx/5xx/excepción /
  "no configurado" sin key, y jamás incluye la key en el resultado.

**Impacto en contrato API (front↔back)**: No (nada expuesto aún).
**Acciones**:
1. TDD-light: tests primero (fallan por módulos inexistentes — razón correcta).
2. Implementar cliente y servicio.
3. Suite completa verde.

**Pruebas / verificación**: pytest verde (línea base + nuevos). Sin envíos reales.
**Riesgos**: ninguno (nada lo consume todavía).

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `feat(back): add resend send client and handoff email builder`

---

## Fase 2 — Email en `cerrar_venta` + disparo del correo al capturar consentimiento

**Proyecto**: backend
**Objetivo**: el cierre por chat exige correo (el bot lo pide si falta), y todo
consentimiento capturado dispara el correo de handoff sin poder romper el cierre.
**Archivos afectados**:
- [conversation.py (schemas)](backend/app/schemas/conversation.py) —
  `ConsentedApplication` gana `email: Optional[str] = None`,
  `handoff_token: Optional[str] = None`, `insurer_name: Optional[str] = None`;
  `ConsentRequest` gana `email: Optional[str] = None` (D4 lo usará).
- [agent_tools.py](backend/app/services/agent_tools.py) — declaración de
  `cerrar_venta`: parámetro `email` (string, descripción "correo del cliente para
  enviarle el link de cierre") y `required: ["consentimiento", "email"]`; handler:
  email ausente o sin formato válido (regex simple `^\S+@\S+\.\S+$`) → error
  controlado `{"error": "falta el correo del cliente", "detail": "pide al cliente su
  correo para enviarle el link de cierre"}` (el LLM lo pide — criterio 2); válido →
  pasarlo a `ConsentService.capture(..., email=email)`.
- [consent.py](backend/app/services/consent.py) — `capture(..., email: str | None =
  None)`: genera `handoff_token` y `insurer_name` (vía `HandoffService`), los guarda
  en la solicitud; si hay `email`, construye y envía el correo con
  `resend_client.send_email` dentro de `try/except` amplio: fallo o `ok: False` →
  `logging.getLogger(__name__).error(...)` (sin key, sin HTML completo) y el cierre
  sigue (criterio 3); sin email → log info "sin correo de destino, no se envía
  handoff" (camino del endpoint estructurado).
- [conversation.py (service)](backend/app/services/conversation.py) —
  `submit_consent` propaga el `email` del `ConsentRequest` a `capture`.
- [orchestrator.py](backend/app/services/orchestrator.py) — regla 4 del
  `SYSTEM_PROMPT` extendida: "...pide el consentimiento explícito Y el correo del
  cliente (ahí le llega el link para finalizar); solo entonces invoca la herramienta
  con ambos".
- Tests (`tests/test_handoff_flow.py` + ajustes mínimos): con LLM guionizado —
  `cerrar_venta` sin email → error controlado y NO se crea solicitud ni se envía
  correo; con email válido → solicitud con `email`/`handoff_token`/`insurer_name`,
  `send_email` (mockeado) llamado una vez con el link que contiene el token; Resend
  devolviendo error / lanzando excepción → la solicitud existe igual, el turno
  termina con texto normal y `caplog` registra el error (criterio 3); endpoint
  `POST /{id}/consent` con `email` en body → correo enviado; sin `email` → 200 igual,
  sin envío; email con formato inválido en la tool → error controlado. Revisar tests
  existentes de `cerrar_venta` guionizado (agregar `email` a los args del guion donde
  aplique — ajuste de expectativa, no debilitamiento).

**Impacto en contrato API (front↔back)**: **Sí — aditivo.** `ConsentedApplication`
(visible en `session.application`) gana `email`/`handoff_token`/`insurer_name`
opcionales y `ConsentRequest` acepta `email` opcional. Nada existente cambia. **Quién
consume el otro lado**: D4 (tarjeta de cierre) y E2 (página `/aseguradora/{token}`),
tareas futuras — nada que actualizar hoy en el front.
**Acciones**:
1. TDD-light: tests primero.
2. Schemas → tool → consent service → conversation service → prompt.
3. Suite completa verde.

**Pruebas / verificación**: pytest verde; **manual en vivo** (criterio 1): uvicorn +
conversación real (o siembra por `POST /profile` + `POST /accept` + `POST /consent`
con `email` para no gastar LLM) con `email` = buzón de la cuenta Resend → el correo
llega en <1 min con producto, prima y link `/aseguradora/{token}`; manual negativo:
tumbar la key (env local inválida) → el consentimiento responde 200/solicitud creada
y el log muestra el error de Resend.
**Riesgos**: entrega de Resend free tier limitada al buzón del dueño de la cuenta
(sin dominio verificado) — para la demo con "correos del equipo" hay que verificar un
dominio en Resend o aceptar el buzón único; latencia del envío (~0.3-1s) se suma al
turno de cierre del chat — aceptable (un turno con tools ya toma 8-12s); si el LLM
inventara un email, la validación de formato no lo detecta — mitigación: la regla 4
pide el correo explícitamente y el turno de confirmación de A5 lo re-lee al cliente.

🛑 **CHECKPOINT** — fin del plan.
**Commit sugerido**: `feat(back): send handoff email on consent capture`

---

## Deuda / fuera de alcance (anotada para el vault)

- **E2**: página `/aseguradora/{token}` (front) + `GET /api/v1/handoff/{token}`
  (backend) + estado `finalizada_demo` — el token y su persistencia quedan listos.
- **D4**: la UI de cierre puede leer `session.application` (email, insurer, token) —
  y una tarjeta `application` tipada seguiría el patrón de D3.
- **E3** (PDF adjunto) y **E4** (confirmación por WhatsApp): se enganchan en el mismo
  punto de disparo de `ConsentService.capture`.
- Reintento de correo fallido: hoy solo log visible (suficiente para MVP); una cola
  simple puede sumarse en E3.
- Verificar dominio propio en Resend para enviar a cualquier correo del equipo/jurado
  (pendiente operativo, no de código).
- Persistencia del token entre redeploys → llega con C3 (Postgres), misma deuda que
  el resto de la sesión.
