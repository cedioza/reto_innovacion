# Plan — Conectividad con terceros + health checks activos por servicio · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-23 · **Tipo**: plan de implementación por fases.
> **Base**: (ninguno — es el primer plan del repo). Insumo externo: decisiones técnicas del
> brain en `colsubsidio-brain/04 - Tecnología/` (`Stack y arquitectura.md`,
> `Canal y costos WhatsApp.md`, `Deuda técnica aceptada.md`).
> **Proyectos afectados**: backend.
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

Que el backend pueda **conectarse con los terceros que la solución requiere** y exponga
un **health check activo por cada uno**, que pruebe la conexión de verdad (no solo que
la app levanta):

- **Gemini API** → hace una llamada real mínima de generación ("ping").
- **WhatsApp Cloud API (número de prueba de Meta)** → **envía un mensaje de prueba**
  a un número registrado del equipo.
- **Postgres (Railway)** → abre conexión y ejecuta `SELECT 1`.
- **Resend** (extra E2–E3, aplazable) → envía un correo de prueba.

Esto da, desde el día 1, un tablero de "¿están vivas mis integraciones?" — clave en un
hackathon donde el demo depende de servicios externos.

## Contexto / hallazgos del análisis

**Terceros que consume el backend en runtime** (de `Stack y arquitectura.md`, sección
"Servicios externos necesarios"): Gemini API (#1), WhatsApp Cloud API (#2), Postgres de
Railway (#3), Resend (#6b, "solo cuando el core esté terminado"). El resto de la lista
(Railway/Vercel/GitHub/cloudflared/UptimeRobot) es infraestructura de deploy, no
servicios que el backend llame — no llevan health check. Telegram es plan B descartado
salvo que Meta falle.

**Env vars ya decididas en el brain** (`Stack y arquitectura.md`, sección de deploy):
`GEMINI_API_KEY`, `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `WHATSAPP_VERIFY_TOKEN`,
`DATABASE_URL`, `FRONTEND_URL`. El health de WhatsApp necesita además un destino de
prueba (`WHATSAPP_TEST_TO`) porque el número de prueba de Meta solo entrega a 5
destinatarios pre-registrados (`Canal y costos WhatsApp.md`).

**Estado actual del backend** (leído completo):

- [main.py](backend/app/main.py) — app FastAPI mínima, CORS y un solo router.
- [health.py](backend/app/api/routes/health.py) — `GET /health` devuelve `{"status": "ok"}`;
  se conserva intacto (lo usa Railway como liveness del deploy).
- [config.py](backend/app/core/config.py#L6-L9) — `Settings` (pydantic-settings) con un
  solo campo `frontend_url`. Toda env var nueva entra aquí (regla de
  [backend/CLAUDE.md](backend/CLAUDE.md)).
- [responses.py](backend/app/helpers/responses.py) — helpers `success_response` /
  `error_response` ya definen el formato estándar; los health checks lo reutilizan.
- [pyproject.toml](backend/pyproject.toml#L6-L16) — runtime: fastapi, uvicorn,
  pydantic-settings. **`httpx` hoy es solo dependencia dev** (para tests); llamar a
  Gemini/WhatsApp lo requiere en runtime → moverlo a `dependencies` (no es dependencia
  "nueva": ya está en el lockfile del venv).
- [test_health.py](backend/tests/test_health.py) — patrón de tests con `TestClient`.
- `services/`, `repositories/`, `models/`, `schemas/` están vacíos (`.gitkeep`).

**Encaje en la arquitectura de capas** (`api → services → repositories → models`):
los clientes de terceros son lógica de integración, no acceso a persistencia → van en
`app/services/integrations/` (un módulo por tercero, con la misma interfaz:
`is_configured()` + `check()`). El router queda delgado en `api/routes/`. Esto además
materializa el principio del brain "proveedor abstraído detrás de una interfaz" y
"adaptador delgado por canal desde el primer commit": el orquestador y el adaptador de
WhatsApp reales crecerán sobre estos mismos módulos.

**Diseño del contrato HTTP** (nuevo, aditivo):

- `GET /health/integrations` — barato y **sin efectos secundarios**: lista cada tercero
  con `configured: true/false` (¿están sus env vars?) sin llamar a nadie. Ideal para
  mirar de un vistazo qué falta por configurar.
- `POST /health/integrations/{service}` — **check activo con efectos reales** (envía
  mensaje de WhatsApp, gasta una llamada de Gemini, envía correo): por eso es POST y no
  GET. Respuestas: `200` con `success_response({service, latency_ms, detail})` si el
  tercero respondió bien; `503` con `error_response` si no está configurado o la llamada
  falló (nunca 500 — toda excepción del cliente HTTP se captura); `404` si el servicio
  no existe.

## Decisiones pendientes (bloqueantes)

(ninguna — resueltas con el usuario el 2026-07-23)

1. ~~Keys de Gemini / Meta / Postgres~~ → el usuario agrega las env vars al `.env`
   durante la implementación y **corre él mismo la verificación manual** contra los
   servicios reales. Los tests automatizados van con mocks (sin red), así que ninguna
   fase se bloquea por keys; sin key, el check responde `503 no configurado`.
2. ~~¿Activar Resend ya?~~ → **sí**: la Fase 5 se ejecuta en esta pasada junto con las
   demás (decisión del usuario; prima sobre el "solo cuando el core esté terminado" del
   brain — la cuenta y API key de Resend se crean cuando se quiera verificar manualmente).

## Principios

- Verde por fase: `pytest` del backend en verde al cierre de cada fase; la app levanta.
- Aditivo antes que destructivo: no se toca `GET /health` existente; todo es nuevo.
- Contrato HTTP explícito; el frontend **no** consume nada de esto todavía (impacto de
  contrato front↔back: ninguno).
- Config solo por env vars vía `Settings`; cada env var nueva actualiza
  [backend/.env.example](backend/.env.example) en la misma fase. Secretos jamás al repo.
- Stack mínimo: única "nueva" dependencia runtime es promover `httpx` de dev a runtime;
  `psycopg` entra solo en la fase de Postgres (inevitable para conectarse). Sin SDKs de
  Google/Meta/Resend: todas son APIs REST simples con httpx.
- Tests sin red: los checks se testean mockeando el cliente HTTP (monkeypatch); la
  verificación contra los servicios reales es manual con `.env` poblado.
- Rutas negativas cubiertas: servicio desconocido → 404, no configurado → 503, tercero
  caído → 503 (nunca 500).

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | backend | Ninguno | 5m | _(sin commit)_ |
| 1 | Base de integraciones + `GET /health/integrations` | backend | Aditivo | 25m | `feat(back): add integrations health status endpoint` |
| 2 | Check activo de Gemini | backend | Aditivo | 20m | `feat(back): add gemini connectivity health check` |
| 3 | Check activo de WhatsApp (mensaje de prueba) | backend | Aditivo | 25m | `feat(back): add whatsapp test message health check` |
| 4 | Check activo de Postgres | backend | Aditivo | 20m | `feat(back): add postgres connectivity health check` |
| 5 | Check activo de Resend | backend | Aditivo | 15m | `feat(back): add resend email health check` |

Total: ~1h50m. Si el tiempo aprieta, las fases 4 y 5 son recortables sin afectar a las
demás (cada check es independiente).

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: backend
**Objetivo**: confirmar que el punto de partida está verde antes de tocar nada.
**Archivos afectados**: ninguno (solo lectura/ejecución).
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` → debe pasar el test de
   `/health` existente.
2. Verificar que la app levanta: `.venv\Scripts\python.exe -m uvicorn app.main:app` y
   `GET /health` responde `{"status": "ok"}`.
3. Verificar si existe `backend/.env` local y qué env vars reales ya hay disponibles
   (keys de Gemini/Meta) — determina hasta dónde llega la verificación manual de las
   fases 2–5.

**Pruebas / verificación**: las de arriba — fase 100 % read-only.
**Riesgos**: ninguno.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit — no hay cambios)_

---

## Fase 1 — Base de integraciones + `GET /health/integrations`

**Proyecto**: backend
**Objetivo**: dejar el andamiaje común (settings, registro de integraciones, schemas,
router) y el endpoint barato que reporta qué tercero está configurado, sin llamar a
ninguno.
**Archivos afectados**:
- [config.py](backend/app/core/config.py) — agregar campos (default `""` = no
  configurado): `gemini_api_key`, `whatsapp_token`, `whatsapp_phone_id`,
  `whatsapp_test_to`, `database_url`, `resend_api_key`, `resend_test_to`.
  (`whatsapp_verify_token` se agregará cuando exista el webhook — no lo usa el health.)
- [.env.example](backend/.env.example) — documentar todas las anteriores con comentario
  de dónde sale cada una (AI Studio, Meta for Developers, Railway, Resend).
- `backend/app/services/integrations/__init__.py` — **nuevo**: registro
  `INTEGRATIONS: dict[str, Integration]` donde cada entrada expone
  `is_configured()` y `check()`; en esta fase los `check()` aún no existen (se
  registran vacíos o con `NotImplemented` → el registro se puebla en fases 2–5).
- `backend/app/schemas/health.py` — **nuevo**: DTOs Pydantic
  (`IntegrationStatus {service, configured, required_env}`,
  `IntegrationCheckResult {service, ok, latency_ms, detail}`).
- `backend/app/api/routes/integrations.py` — **nuevo**: router con prefijo
  `/health/integrations`; en esta fase solo `GET /` (lista estados usando
  `is_configured()`, formato `success_response`).
- [main.py](backend/app/main.py) — registrar el router nuevo.
- [pyproject.toml](backend/pyproject.toml) — mover `httpx` de `[dev]` a
  `dependencies` (lo usan los checks de las fases 2, 3 y 5).
- `backend/tests/test_integrations_health.py` — **nuevo**.

**Impacto en contrato API (front↔back)**: No (endpoint nuevo aditivo; el frontend no lo
consume aún — si luego se quiere un panelcito de estado en el front, será otro plan).
**Acciones**:
1. Extender `Settings` y `.env.example` (env vars arriba).
2. Crear `schemas/health.py` con los dos DTOs.
3. Crear `services/integrations/__init__.py` con la interfaz común y el registro (por
   ahora: nombre → env vars requeridas; los `check()` llegan en fases 2–5).
4. Crear el router `GET /health/integrations` y registrarlo en `main.py`.
5. Mover `httpx` a runtime en `pyproject.toml` y reinstalar (`pip install -e .[dev]`)
   — **lo hace el usuario o el orquestador con aprobación**, no los agentes (regla:
   agentes no instalan dependencias).
6. Tests: `GET /health/integrations` → 200, incluye los 4 servicios, `configured` es
   `false` sin env vars y `true` con env vars fake (override de `Settings` en el test);
   `GET /health` sigue intacto.

**Pruebas / verificación**: `.venv\Scripts\python.exe -m pytest -q` verde; levantar
uvicorn y `curl http://localhost:8000/health/integrations`.
**Riesgos**: `Settings` se instancia a nivel de módulo — si un `.env` local tiene keys
reales, los tests deben hacer override explícito para no depender del entorno.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `feat(back): add integrations health status endpoint`

---

## Fase 2 — Check activo de Gemini

**Proyecto**: backend
**Objetivo**: `POST /health/integrations/gemini` prueba la conexión real: llamada
mínima a `generateContent` (modelo flash, prompt "ping", `maxOutputTokens` bajo) contra
`https://generativelanguage.googleapis.com` con la `GEMINI_API_KEY`.
**Archivos afectados**:
- `backend/app/services/integrations/gemini.py` — **nuevo**: cliente REST con httpx
  (timeout ~10 s), sin SDK; devuelve `IntegrationCheckResult`.
- `backend/app/services/integrations/__init__.py` — registrar su `check()`.
- `backend/app/api/routes/integrations.py` — agregar `POST /{service}`: resuelve en el
  registro (404 si no existe), ejecuta `check()`, mapea ok → 200 / fallo o no
  configurado → 503 con `error_response`. **Este handler es genérico: las fases 3–5 ya
  no tocan el router.**
- `backend/tests/test_integrations_health.py` — ampliar.

**Impacto en contrato API (front↔back)**: No (aditivo, sin consumidor front).
**Acciones**:
1. Implementar `gemini.py`: sin key → resultado "no configurado"; con key → POST a
   `generateContent`; capturar `httpx.HTTPError` y status ≠ 2xx → resultado con detalle
   del error (sin filtrar la key en el mensaje).
2. Agregar el handler genérico `POST /health/integrations/{service}`.
3. Tests (mock de `httpx.Client` vía monkeypatch): éxito → 200 con `latency_ms`;
   Gemini caído/4xx → 503 (no 500); sin key → 503 "no configurado";
   `POST /health/integrations/noexiste` → 404.

**Pruebas / verificación**: pytest verde; manual (si hay key en `.env`):
`curl -X POST http://localhost:8000/health/integrations/gemini` → 200 y `latency_ms`
real. Sin key → 503 con mensaje claro.
**Riesgos**: gasta una llamada por check — irrelevante con los créditos del kit; el
prompt "ping" con `maxOutputTokens` mínimo lo mantiene despreciable.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 3 sin aprobación del usuario.
**Commit sugerido**: `feat(back): add gemini connectivity health check`

---

## Fase 3 — Check activo de WhatsApp (mensaje de prueba)

**Proyecto**: backend
**Objetivo**: `POST /health/integrations/whatsapp` **envía un mensaje de texto real**
("health check ✅ + timestamp") vía Cloud API
(`https://graph.facebook.com/v20.0/{WHATSAPP_PHONE_ID}/messages`) al número
`WHATSAPP_TEST_TO` (uno de los 5 pre-registrados del número de prueba de Meta). Si el
mensaje llega al teléfono, la integración está viva de punta a punta.
**Archivos afectados**:
- `backend/app/services/integrations/whatsapp.py` — **nuevo**: cliente REST httpx
  (auth Bearer `WHATSAPP_TOKEN`); devuelve `IntegrationCheckResult` (incluye el
  `message_id` de Meta en `detail` cuando hay éxito).
- `backend/app/services/integrations/__init__.py` — registrarlo.
- `backend/tests/test_integrations_health.py` — ampliar.

**Impacto en contrato API (front↔back)**: No (aditivo).
**Acciones**:
1. Implementar `whatsapp.py`: requiere `whatsapp_token`, `whatsapp_phone_id` y
   `whatsapp_test_to`; si falta cualquiera → "no configurado". Payload
   `type: "text"` (dentro de la ventana de servicio del número de prueba funciona sin
   plantilla).
2. Tests con mock: éxito (respuesta con `messages[0].id`) → 200; token inválido /
   destinatario no registrado (error 4xx de Meta) → 503 con el mensaje de error de Meta
   en `details`; sin config → 503.

**Pruebas / verificación**: pytest verde; manual (con app de Meta creada):
`curl -X POST http://localhost:8000/health/integrations/whatsapp` → 200 **y el mensaje
llega al teléfono del equipo** — esa es la prueba definitiva pedida.
**Riesgos**: el número de prueba solo entrega a destinatarios pre-registrados; si Meta
devuelve 200 pero el mensaje no llega, revisar que `WHATSAPP_TEST_TO` esté registrado y
con el código de verificación confirmado. Este servicio (el cliente httpx) es la semilla
del adaptador de canal WhatsApp real — mismo módulo, se le sumará el webhook después.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 4 sin aprobación del usuario.
**Commit sugerido**: `feat(back): add whatsapp test message health check`

---

## Fase 4 — Check activo de Postgres

**Proyecto**: backend
**Objetivo**: `POST /health/integrations/postgres` abre conexión a `DATABASE_URL` y
ejecuta `SELECT 1`. Valida la BD de Railway (o local) antes de que exista cualquier
modelo.
**Archivos afectados**:
- [pyproject.toml](backend/pyproject.toml) — agregar `psycopg[binary]` (driver mínimo;
  SQLModel/SQLAlchemy llegarán cuando haya modelos, no antes).
- `backend/app/services/integrations/database.py` — **nuevo**: `psycopg.connect(...,
  connect_timeout=5)` + `SELECT 1`; devuelve `IntegrationCheckResult`.
- `backend/app/services/integrations/__init__.py` — registrarlo.
- `backend/tests/test_integrations_health.py` — ampliar (mock de `psycopg.connect`).

**Impacto en contrato API (front↔back)**: No (aditivo).
**Acciones**:
1. Agregar `psycopg[binary]` (instala el usuario/orquestador con aprobación).
2. Implementar `database.py`: sin `DATABASE_URL` → "no configurado"; error de conexión
   → resultado con el error (sin credenciales en el mensaje).
3. Tests: mock de conexión ok → 200; `OperationalError` → 503; sin URL → 503.

**Pruebas / verificación**: pytest verde; manual: con la `DATABASE_URL` de Railway en
`.env`, `curl -X POST http://localhost:8000/health/integrations/postgres` → 200.
**Riesgos**: si el Postgres de Railway aún no está provisionado, ejecutar la fase igual
deja el check listo y respondiendo `503 no configurado`; el usuario lo verifica cuando
agregue la `DATABASE_URL` a su `.env`.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 5 sin aprobación del usuario.
**Commit sugerido**: `feat(back): add postgres connectivity health check`

---

## Fase 5 — Check activo de Resend

**Proyecto**: backend
**Objetivo**: `POST /health/integrations/resend` envía un correo de prueba real vía
`https://api.resend.com/emails` a `RESEND_TEST_TO`. (El brain la condicionaba a "core
terminado"; el usuario decidió incluirla en esta pasada — decisión resuelta #2.)
**Archivos afectados**:
- `backend/app/services/integrations/resend.py` — **nuevo**: cliente REST httpx (auth
  Bearer `RESEND_API_KEY`, remitente `onboarding@resend.dev` del free tier).
- `backend/app/services/integrations/__init__.py` — registrarlo.
- `backend/tests/test_integrations_health.py` — ampliar.

**Impacto en contrato API (front↔back)**: No (aditivo).
**Acciones**:
1. Implementar `resend.py` con el mismo patrón (no configurado / éxito con `email_id` /
   error → 503).
2. Tests con mock, mismos tres casos.

**Pruebas / verificación**: pytest verde; manual: correo de prueba llega al buzón.
**Riesgos**: free tier 100 correos/día — de sobra para checks manuales.

🛑 **CHECKPOINT** — fin del plan.
**Commit sugerido**: `feat(back): add resend email health check`
