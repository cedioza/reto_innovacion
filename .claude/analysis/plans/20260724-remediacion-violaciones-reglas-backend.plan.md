# Plan — Remediación de violaciones a las reglas del repo (backend) · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-24 · **Tipo**: plan de implementación por fases.
> **Base**: [20260723-health-terceros-backend.plan.md](.claude/analysis/plans/20260723-health-terceros-backend.plan.md)
> (estableció el patrón de config vía `Settings`, POST para acciones con efectos, y
> tests con mocks sin red — este plan aplica esos mismos principios al código nuevo).
> **Proyectos afectados**: backend.
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

Corregir las 5 violaciones a las reglas del repo introducidas en el commit `662e518`
(`feat(backend): add YCloud WhatsApp integration`, ~2.680 líneas), sin cambiar el
comportamiento funcional del bot:

1. **URL hardcodeada** — [webhooks.py:164](backend/app/api/routes/webhooks.py#L164)
   usa el placeholder `"https://tu-dominio.com"` y reutiliza `FRONTEND_URL` (que el
   contrato del repo reserva para CORS) como URL pública del backend.
2. **Token con default hardcodeado** — `whatsapp_verify_token = "colsubsidio-reto-2026"`
   en [config.py:20](backend/app/core/config.py#L20) y commiteado en
   [.env.example](backend/.env.example).
3. **`os.getenv` fuera de `core/`** — [affiliates.py:23-26](backend/app/repositories/affiliates.py#L23-L26)
   lee `AFFILIATE_CSV_PATH` directo del entorno, violando la regla de `backend/CLAUDE.md`
   ("toda variable de entorno se lee vía `Settings`").
4. **Capas** — repositorios importan `schemas`
   ([applications.py:8](backend/app/repositories/applications.py#L8),
   [conversations.py:9](backend/app/repositories/conversations.py#L9)) — import "hacia
   arriba" prohibido; y [webhooks.py:176](backend/app/api/routes/webhooks.py#L176) hace
   la llamada HTTP a Telegram directamente en el router (lógica de integración en `api/`).
5. **Commits pequeños** — el commit `662e518` mezcla ~10 features; la regla pide un
   cambio lógico por commit.

## Contexto / hallazgos del análisis

**Radio de impacto real de cada violación** (código leído completo, callers rastreados):

- **`/webhooks/telegram/set`** ([webhooks.py:157-179](backend/app/api/routes/webhooks.py#L157-L179)):
  es un endpoint de conveniencia operativa (registra el webhook ante Telegram). Nadie lo
  consume — ni el frontend ni ningún test lo cubre. Es `GET` con efectos secundarios
  (contradice el precedente del plan base: POST para acciones con efectos). Deriva la
  URL pública de `settings.frontend_url` y cae al placeholder si detecta localhost.
  Además llama `httpx.get` en el router (violación 4c) — el fix natural resuelve 1 y 4c
  juntos: mover la lógica a [telegram_client.py](backend/app/services/telegram_client.py)
  (que ya existe y ya encapsula `sendMessage`) y leer la URL pública de una env var nueva.
- **Verify token** ([webhooks.py:22-31](backend/app/api/routes/webhooks.py#L22-L31)):
  el handler compara `hub.verify_token` contra `settings.whatsapp_verify_token`. Con el
  default hardcodeado, cualquiera que lea el repo público puede verificar un webhook
  contra la app. Ningún test ni módulo depende del valor default (grep en `tests/` y
  `app/`: cero referencias a `colsubsidio-reto-2026` fuera de config y `.env.example`).
  El fix es default `""` + **fail-closed**: si el setting está vacío, responder 403
  siempre (hoy, con setting vacío y `hub.verify_token` vacío, la comparación `"" == ""`
  daría 200 — agujero adicional que el fail-closed cierra).
- **CSV de afiliados** ([affiliates.py:23-26](backend/app/repositories/affiliates.py#L23-L26)):
  los 2 tests que tocan rutas de CSV inyectan `csv_path` por constructor
  ([test_affiliates.py:24](backend/tests/test_affiliates.py#L24)), así que mover la
  lectura del entorno a `Settings` **no rompe ningún test**. `AFFILIATE_CSV_PATH` además
  no está documentada en `.env.example` (violación doble: lectura directa + env var sin
  documentar).
- **Repos → schemas**: [ApplicationRepository](backend/app/repositories/applications.py)
  y [ConversationRepository](backend/app/repositories/conversations.py) son diccionarios
  en memoria que almacenan DTOs Pydantic (`ConsentedApplication`, `ConversationResponse`).
  Sus únicos callers son [consent.py:20](backend/app/services/consent.py#L20),
  [conversation.py:27](backend/app/services/conversation.py#L27) y sus tests. El
  almacenamiento es opaco (los repos nunca inspeccionan campos del objeto, solo
  `session.session_id` en `ConversationRepository.save`).
- **Services → models**: `affiliate.py`, `catalog.py`, `propensity.py` y `quote.py`
  importan de `app/models/`. Leyendo `backend/CLAUDE.md` completo, esto es un import
  **hacia abajo** (services está por encima de repositories/models en la cadena
  `api → services → repositories → models`) y es el patrón que hace posible que los
  repos devuelvan models y los services los conviertan a schemas — exactamente lo que
  hace [conversation.py:50-57](backend/app/services/conversation.py#L50-L57) con
  `AffiliateProfile → ProfileData`. La frase "models: solo los usa `repositories/`" del
  CLAUDE.md contradice su propia regla de dirección; la interpretación consistente es
  "models nunca suben a `api/` ni se exponen en la API". Este plan **no** refactoriza
  los services: propone aclarar la regla en la fase de docs (con tu aprobación en el
  checkpoint) y corregir solo el import hacia arriba de los repos, que sí es inequívoco.
- **Commit gigante**: `662e518` ya está **pusheado** y es la base de la rama remota
  default (`origin/feat/backend-ycloud-llm-validation`). Reescribir historia sería
  destructivo para tu compañero. La violación se remedia **hacia adelante**: cada fase
  de este plan produce un commit pequeño de un solo cambio lógico (y la fase de docs
  deja el recordatorio explícito).
- **Estado del entorno**: el fork **no tiene `.venv`** (`backend/.venv` no existe). La
  suite (109 tests) pasa en verde ejecutada con el venv del repo original vía
  `PYTHONPATH` — la Fase 0 crea el venv propio del fork para no depender de eso.
- **Hallazgo adyacente (fuera de las 5 violaciones, opcional)**: el webhook
  [POST /webhooks/telegram](backend/app/api/routes/webhooks.py#L140-L154) nunca valida
  el header `X-Telegram-Bot-Api-Secret-Token` aunque `TELEGRAM_WEBHOOK_SECRET` existe en
  config precisamente para eso ([.env.example](backend/.env.example) lo documenta).
  Cualquiera que conozca la URL puede inyectar mensajes. Se incluye como Fase 6
  (recortable) por ser de la misma familia que las violaciones 1-2.

**Impacto en contrato front↔back: ninguno.** El frontend no consume webhooks ni
`/api/v1/conversations` todavía; las env vars nuevas (`BACKEND_PUBLIC_URL`,
`AFFILIATE_CSV_PATH`) son solo del backend.

## Decisiones pendientes (bloqueantes)

1. **Cómo desacoplar los repos de los schemas (bloquea solo la Fase 4).** Dos opciones:
   - **(A — recomendada)** Repos **genéricos/opacos**: los repos almacenan el objeto sin
     importar su tipo (firma explícita `save(session_id: str, obj)` con type hints
     genéricos). ~15 líneas de cambio, cero duplicación. Los DTOs siguen definidos en
     `schemas/` y los services siguen siendo dueños de la conversión. Encaja con el
     carácter en-memoria/hackathon de estos repos.
   - **(B)** Crear **models espejo** (`models/conversation.py`, `models/application.py`
     como dataclasses) + conversores model↔schema en los services. Es la forma canónica
     con persistencia real, pero duplica ~6 clases Pydantic como dataclasses (~150
     líneas) que habrá que rehacer cuando entre SQLModel/Postgres ("stage two" ya
     anunciado en [webhooks.py:18](backend/app/api/routes/webhooks.py#L18)).
   El plan está escrito para la opción A; si prefieres B, la Fase 4 se re-estima (~45m).

_(Resuelta en el análisis: **no** se reescribe la historia de git del commit `662e518`
— está pusheado y es la rama base remota; la regla de commits pequeños se aplica hacia
adelante.)_

## Principios

- Verde por fase: `pytest` del backend en verde al cierre de cada fase; la app levanta.
- **Comportamiento funcional intacto**: esto es remediación, no re-diseño. El flujo del
  bot (webhooks → channel_handler → conversación) no cambia de semántica, salvo los dos
  cierres de seguridad explícitos (fail-closed del verify token, Fase 1; secret de
  Telegram, Fase 6 opcional).
- Config solo por env vars vía `Settings`; toda env var nueva entra a
  [.env.example](backend/.env.example) en la misma fase. Secretos jamás al repo.
- Sin dependencias nuevas (cero: todo es refactor sobre lo existente).
- Aditivo antes que destructivo: primero se agregan settings y services, al final se
  ajustan reglas/docs.
- Un cambio lógico por commit — cada fase es un commit pequeño y revisable (remediación
  de la violación 5 por la vía práctica).
- Tests sin red (mocks/monkeypatch, patrón ya establecido en
  [test_ycloud_webhooks.py](backend/tests/test_ycloud_webhooks.py)).

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight: venv del fork + línea base verde | backend | Ninguno | 10m | _(sin commit)_ |
| 1 | Verify token sin default + fail-closed | backend | Bajo | 15m | `fix(back): remove hardcoded whatsapp verify token default` |
| 2 | `AFFILIATE_CSV_PATH` vía `Settings` | backend | Bajo | 10m | `refactor(back): read affiliate csv path via settings` |
| 3 | `BACKEND_PUBLIC_URL` + setWebhook al service | backend | Medio | 25m | `refactor(back): move telegram setwebhook to service layer` |
| 4 | Repos sin imports de schemas | backend | Medio | 20m | `refactor(back): decouple repositories from schemas` |
| 5 | Docs: aclarar regla de models y granularidad de commits | backend | Ninguno | 10m | `docs: clarify backend layer rules for models` |
| 6 | _(opcional/recortable)_ Validar secret del webhook Telegram | backend | Bajo | 15m | `fix(back): validate telegram webhook secret header` |
| 7 | `QuoteService` consume `CatalogService` (no el repo ajeno) | backend | Bajo | 10m | `refactor(back): quote service uses catalog service` |
| 8 | Instancia única de `ConversationService` entre canales | backend | Medio | 20m | `refactor(back): share conversation service across channels` |

Total: ~2h15m (1h30m con solo el núcleo). Si el tiempo aprieta: la Fase 5 es solo docs
y las Fases 6-8 son opcionales; las Fases 1-4 son el núcleo de la remediación y son
independientes entre sí (cualquiera puede aplazarse sin bloquear a las demás).

---

## Fase 0 — Pre-flight: venv del fork + línea base verde

**Proyecto**: backend
**Objetivo**: dar al fork un entorno propio (hoy no tiene `.venv`) y confirmar la línea
base verde antes de tocar nada.
**Archivos afectados**: ninguno del repo (solo `backend/.venv/`, que está ignorado).
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Desde `backend/`: `python -m venv .venv` y
   `.venv\Scripts\python.exe -m pip install -e .[dev]` — **lo ejecuta el usuario u
   orquestador con aprobación** (regla: los agentes no instalan dependencias).
2. `.venv\Scripts\python.exe -m pytest -q` → **109 tests en verde** (línea base
   verificada el 2026-07-24 con el venv del repo original).
3. Levantar `uvicorn app.main:app` y verificar `GET /health` → `{"status": "ok"}`.

**Pruebas / verificación**: las de arriba — fase 100 % read-only respecto al código.
**Riesgos**: ninguno.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit — no hay cambios en el repo)_

---

## Fase 1 — Verify token sin default + fail-closed

**Proyecto**: backend
**Objetivo**: eliminar el token hardcodeado `"colsubsidio-reto-2026"` del repo y cerrar
el agujero de verificación con setting vacío (violación 2).
**Archivos afectados**:
- [config.py:20](backend/app/core/config.py#L20) — `whatsapp_verify_token: str = ""`.
- [.env.example](backend/.env.example) — `WHATSAPP_VERIFY_TOKEN=` vacío, con comentario
  "genera un valor aleatorio propio; sin él, la verificación del webhook responde 403".
- [webhooks.py:22-31](backend/app/api/routes/webhooks.py#L22-L31) — fail-closed: si
  `settings.whatsapp_verify_token` está vacío → 403 incondicional (hoy `"" == ""`
  pasaría la verificación).
- [test_ycloud_webhooks.py](backend/tests/test_ycloud_webhooks.py) o archivo nuevo
  `tests/test_whatsapp_webhook_verify.py` — cubrir el `GET /webhooks/whatsapp` (hoy sin
  tests).

**Impacto en contrato API (front↔back)**: No. (Operativo: si el deploy de Railway
dependía del default, hay que setear `WHATSAPP_VERIFY_TOKEN` en el entorno del deploy —
solo afecta al proveedor `meta`; el flujo actual usa `ycloud`, que no pasa por esta
verificación.)
**Acciones**:
1. Cambiar el default en `Settings` a `""` y actualizar `.env.example`.
2. Agregar el guard fail-closed en `verify_whatsapp_webhook`.
3. Tests (con `monkeypatch.setattr(settings, ...)`, patrón existente): token
   configurado + match → 200 con el challenge; token configurado + mismatch → 403;
   token vacío (incluso con `hub.verify_token` vacío) → 403.

**Pruebas / verificación**: `.venv\Scripts\python.exe -m pytest -q` verde; el valor
`colsubsidio-reto-2026` desaparece de `git grep` en el working tree.
**Riesgos**: quien tenga el default en su `.env` o en Railway debe regenerarlo — es
deseable: el valor actual está quemado en la historia pública del repo.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `fix(back): remove hardcoded whatsapp verify token default`

---

## Fase 2 — `AFFILIATE_CSV_PATH` vía `Settings`

**Proyecto**: backend
**Objetivo**: eliminar el `os.getenv` de la capa de repositorios (violación 3) y
documentar la env var que hoy existe sin estar en `.env.example`.
**Archivos afectados**:
- [config.py](backend/app/core/config.py) — campo `affiliate_csv_path: str = ""`.
- [.env.example](backend/.env.example) — `AFFILIATE_CSV_PATH=` con comentario (ruta al
  CSV anonimizado de afiliados; vacío = default `backend/app/data/afiliados.csv`).
- [affiliates.py:17-33](backend/app/repositories/affiliates.py#L17-L33) — quitar
  `import os` y el `os.getenv`; el constructor resuelve:
  `csv_path` explícito → `settings.affiliate_csv_path` (si no vacío) → default
  `Path(__file__)...` que ya calcula hoy.

**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Agregar el campo a `Settings` y la entrada a `.env.example`.
2. Refactorizar la resolución de ruta en `AffiliateRepository.__init__`.
3. Test nuevo en [test_affiliates.py](backend/tests/test_affiliates.py): con
   `monkeypatch.setattr(settings, "affiliate_csv_path", <tmp>)` el repo (sin `csv_path`
   explícito) lee de esa ruta. Los tests existentes no cambian (inyectan `csv_path`
   por constructor).

**Pruebas / verificación**: pytest verde; `grep os.getenv backend/app` solo devuelve
resultados fuera de `repositories/` (idealmente ninguno fuera de `core/`).
**Riesgos**: ninguno — mismo default, misma precedencia efectiva.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 3 sin aprobación del usuario.
**Commit sugerido**: `refactor(back): read affiliate csv path via settings`

---

## Fase 3 — `BACKEND_PUBLIC_URL` + setWebhook al service

**Proyecto**: backend
**Objetivo**: eliminar el placeholder `"https://tu-dominio.com"` y el uso indebido de
`FRONTEND_URL` como URL pública del backend (violación 1), y sacar la llamada HTTP del
router (violación 4c).
**Archivos afectados**:
- [config.py](backend/app/core/config.py) — campo `backend_public_url: str = ""`.
- [.env.example](backend/.env.example) — `BACKEND_PUBLIC_URL=` con comentario (URL
  pública HTTPS del backend desplegado, ej. la de Railway; requerida solo para
  registrar el webhook de Telegram).
- [telegram_client.py](backend/app/services/telegram_client.py) — nueva función
  `set_telegram_webhook() -> dict`: construye
  `{backend_public_url}/webhooks/telegram`, llama al Bot API `setWebhook` (httpx,
  timeout 10s, adjunta `secret_token` si `telegram_webhook_secret` está configurado) y
  devuelve el resultado; sin token o sin URL pública → resultado de error sin llamar a
  nadie. **Nunca** incluir la URL del Bot API (contiene el token) en mensajes de error
  — regla heredada del plan base.
- [webhooks.py:157-179](backend/app/api/routes/webhooks.py#L157-L179) — el handler
  queda delgado: delega al service y mapea el resultado (no configurado → 503 en vez de
  llamar con placeholder). Cambiar `GET /telegram/set` → `POST /telegram/set` (acción
  con efectos; precedente del plan base; sin consumidores conocidos — ver riesgos).
- `tests/test_telegram_webhook_setup.py` — **nuevo** (el endpoint hoy no tiene tests).

**Impacto en contrato API (front↔back)**: No (el frontend no lo consume; env var nueva
solo backend).
**Acciones**:
1. Agregar `backend_public_url` a `Settings` y `.env.example`.
2. Implementar `set_telegram_webhook()` en el service.
3. Adelgazar el router: `POST /webhooks/telegram/set` → service → 200 con la respuesta
   de Telegram / 503 si falta `telegram_bot_token` o `backend_public_url`.
4. Tests (mock de `httpx` vía monkeypatch): sin token → 503; sin URL pública → 503
   (jamás placeholder); configurado → llama a la URL correcta de setWebhook (incluye
   `secret_token` cuando existe) y devuelve el JSON de Telegram; error de red → 503,
   nunca 500, y el mensaje no contiene el bot token.

**Pruebas / verificación**: pytest verde; `git grep "tu-dominio"` vacío; manual (si hay
bot token y URL de Railway en `.env`):
`curl -X POST http://localhost:8000/webhooks/telegram/set` → respuesta de Telegram.
**Riesgos**: si alguien (tu compañero) usaba `GET /telegram/set` a mano desde el
navegador, ahora es POST — avisarle en el checkpoint; es un endpoint operativo interno,
no de producto.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 4 sin aprobación del usuario.
**Commit sugerido**: `refactor(back): move telegram setwebhook to service layer`

---

## Fase 4 — Repos sin imports de schemas

**Proyecto**: backend
**Objetivo**: eliminar los imports "hacia arriba" (`repositories` → `schemas`) en
[applications.py:8](backend/app/repositories/applications.py#L8) y
[conversations.py:9](backend/app/repositories/conversations.py#L9) (violación 4a-4b),
según la **opción A** (repos genéricos/opacos — ver Decisiones pendientes).
**Archivos afectados**:
- [conversations.py](backend/app/repositories/conversations.py) — quitar el import de
  `ConversationResponse`; firma explícita `save(session_id: str, session) -> None`
  (deja de leer `session.session_id` dentro del repo: el ID lo pasa el caller).
- [applications.py](backend/app/repositories/applications.py) — quitar el import de
  `ConsentedApplication`; los hints quedan genéricos (el repo ya trata el objeto como
  opaco).
- [conversation.py](backend/app/services/conversation.py) — actualizar los 4 call sites
  de `self._repo.save(session)` → `self._repo.save(session.session_id, session)`.
- [test_conversation_repository.py](backend/tests/test_conversation_repository.py) y
  [test_applications_repository.py](backend/tests/test_applications_repository.py) —
  ajustar a la firma nueva (los tests siguen construyendo los DTOs de `schemas/`: los
  tests no son una capa y pueden importar lo que verifiquen).

**Impacto en contrato API (front↔back)**: No (refactor interno; las respuestas HTTP no
cambian de shape).
**Acciones**:
1. Refactorizar ambos repos (sin imports de `app.schemas`).
2. Actualizar `ConversationService` a la firma nueva.
3. Ajustar los dos archivos de tests de repositorios; correr la suite completa.

**Pruebas / verificación**: pytest verde (los 13 archivos de tests del flujo cubren la
regresión); `grep "from app.schemas" backend/app/repositories/` vacío.
**Riesgos**: perder el type-checking estático en los repos — aceptado en la opción A
(repos en memoria que se reemplazarán por Postgres en el "stage two" ya anunciado). Si
se prefiere la opción B (models espejo), re-estimar a ~45m antes de iniciar la fase.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 5 sin aprobación del usuario.
**Commit sugerido**: `refactor(back): decouple repositories from schemas`

---

## Fase 5 — Docs: aclarar regla de models y granularidad de commits

**Proyecto**: backend
**Objetivo**: cerrar la ambigüedad de `backend/CLAUDE.md` que hace ver como violación
el patrón legítimo services→models (violación 4b: los imports de `models/` en
`affiliate.py`, `catalog.py`, `propensity.py`, `quote.py` son hacia abajo y necesarios
para que los services conviertan model→schema), y dejar por escrito el recordatorio de
commits pequeños tras el episodio `662e518`.
**Archivos afectados**:
- [backend/CLAUDE.md](backend/CLAUDE.md) — reescribir la línea de `app/models/`:
  "modelos de persistencia. Los produce/consume `repositories/`; los services pueden
  recibirlos y convertirlos a schemas; **nunca** llegan a `api/` ni se exponen en la
  API". (Cambia la redacción, no la arquitectura.)
- _(opcional, mismo commit)_ una línea en la sección de commits de
  [CLAUDE.md](CLAUDE.md) o nota en el plan: features grandes se parten por fases/commits.

**Impacto en contrato API (front↔back)**: No (solo documentación).
**Acciones**:
1. Redactar el ajuste y presentarlo en el checkpoint — **es un cambio de regla del
   repo: requiere tu visto bueno explícito y, idealmente, el de tu compañero**.
2. Si en cambio decides que la regla estricta se mantiene (services jamás importan
   models), este plan necesita una fase adicional de refactor (repos devuelven schemas
   construidos... lo cual reintroduce la violación 4a) — hallazgo del análisis: ambas
   reglas literales son mutuamente incompatibles; una de las dos redacciones debe ceder.

**Pruebas / verificación**: n/a (docs); pytest sigue verde.
**Riesgos**: ninguno técnico; es una decisión de convenciones de equipo.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 6 sin aprobación del usuario.
**Commit sugerido**: `docs: clarify backend layer rules for models`

---

## Fase 6 — _(opcional)_ Validar secret del webhook de Telegram

_Fuera de las 5 violaciones reportadas, pero de la misma familia (endpoints webhook
abiertos): hallazgo del análisis del 2026-07-24._

**Proyecto**: backend
**Objetivo**: que [POST /webhooks/telegram](backend/app/api/routes/webhooks.py#L140-L154)
valide el header `X-Telegram-Bot-Api-Secret-Token` contra
`settings.telegram_webhook_secret` (que ya existe en config y ya se registra ante
Telegram en el `setWebhook` de la Fase 3) — hoy cualquiera que conozca la URL puede
inyectar mensajes y hacer que el bot responda por Telegram.
**Archivos afectados**:
- [webhooks.py:140-154](backend/app/api/routes/webhooks.py#L140-L154) — guard al inicio
  del handler: si `telegram_webhook_secret` está configurado y el header no coincide
  (`hmac.compare_digest`) → 401. Si no está configurado, comportamiento actual (mismo
  patrón permisivo-explícito que `ycloud_allow_unsigned_webhooks`).
- `tests/test_telegram_webhook.py` — **nuevo**: secret configurado + header correcto →
  200 y procesa; header ausente/incorrecto → 401 y **no** llama al handler; secret
  vacío → 200 (compatibilidad).

**Impacto en contrato API (front↔back)**: No.
**Acciones**: las de arriba (guard + 3 tests con monkeypatch).
**Pruebas / verificación**: pytest verde; manual: mensaje real al bot sigue llegando
tras re-registrar el webhook con `secret_token`.
**Riesgos**: si el webhook en producción se registró sin `secret_token`, configurar el
secret en `.env` sin re-ejecutar `/webhooks/telegram/set` dejaría de aceptar updates
reales de Telegram → el checkpoint recuerda re-registrar.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 7 sin aprobación del usuario.
**Commit sugerido**: `fix(back): validate telegram webhook secret header`

---

## Fase 7 — `QuoteService` consume `CatalogService` (no el repo ajeno)

_Fases 7-8 agregadas el 2026-07-24, tras ejecutar las fases 0-6, a pedido del usuario:
hallazgos de la revisión de la convención "un service solo consume su propio repo y
otros services" (regla añadida a [backend/CLAUDE.md](backend/CLAUDE.md) en esa misma
fecha; commitear la regla junto con esta fase o con la Fase 5)._

**Proyecto**: backend
**Objetivo**: [quote.py:16](backend/app/services/quote.py#L16) instancia
`CatalogRepository` directamente — el repo de otra entidad — mientras
[CatalogService](backend/app/services/catalog.py), que existe para envolver ese repo,
no tiene ningún consumidor (código muerto). Alinear con la regla de ownership.
**Archivos afectados**:
- [quote.py](backend/app/services/quote.py) — `self._catalog = CatalogService()`;
  las llamadas `get_product(...)` mantienen la misma interfaz (el service es un wrapper
  delgado del repo, firmas idénticas).
- [test_quote.py](backend/tests/test_quote.py) — revisar; solo cambia si mockea o
  inyecta el repo directamente.

**Impacto en contrato API (front↔back)**: No (refactor interno; las cotizaciones no
cambian de valor ni de shape).
**Acciones**:
1. Cambiar el import y la instanciación en `QuoteService`.
2. Verificar con grep que ningún service importe repositorios de otra entidad
   (`grep "from app.repositories" backend/app/services/` → cada service solo el suyo).
3. Suite completa en verde.

**Pruebas / verificación**: pytest verde (línea base al cierre de la Fase 6: 121).
**Riesgos**: ninguno — `CatalogService` y `CatalogRepository` exponen las mismas
firmas (`get_product`, `list_products`); el catálogo es de solo lectura.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 8 sin aprobación del usuario.
**Commit sugerido**: `refactor(back): quote service uses catalog service`

---

## Fase 8 — Instancia única de `ConversationService` entre canales

**Proyecto**: backend
**Objetivo**: hoy hay **dos almacenes de sesiones paralelos e invisibles entre sí**:
[conversations.py:19](backend/app/api/routes/conversations.py#L19) crea un
`ConversationService()` para la API REST, y
[channel_handler.py:76](backend/app/services/channel_handler.py#L76) crea **otro**
dentro del `ChannelHandler` de los webhooks. Como los repos son diccionarios en memoria
por instancia, una sesión creada por `POST /api/v1/conversations` no existe para el
flujo de WhatsApp/Telegram y viceversa. Compartir UNA instancia entre ambos puntos de
entrada.
**Archivos afectados**:
- [conversation.py](backend/app/services/conversation.py) — exponer una instancia
  módulo-level `conversation_service = ConversationService()` (patrón singleton simple,
  mismo estilo que `settings` en `core/config.py`).
- [conversations.py](backend/app/api/routes/conversations.py) — usar la instancia
  compartida en lugar de crear una propia.
- [channel_handler.py](backend/app/services/channel_handler.py) — `ChannelHandler`
  acepta el service por parámetro con default a la instancia compartida
  (`def __init__(self, service=None): self._service = service or conversation_service`)
  para mantener testabilidad.
- Tests del flujo ([test_conversations_router.py](backend/tests/test_conversations_router.py),
  [test_e2e_happy_path.py](backend/tests/test_e2e_happy_path.py),
  [test_conversation_service.py](backend/tests/test_conversation_service.py)) — revisar
  aislamiento: con almacén compartido, sesiones de un test son visibles en otro; los
  `session_id` son UUID así que no deberían chocar, pero cualquier aserción sobre
  conteos (`count()`) necesita fixture de limpieza o repo propio inyectado.

**Impacto en contrato API (front↔back)**: No (mismas rutas y shapes; cambia la
consistencia interna: los canales ven las mismas sesiones).
**Acciones**:
1. Crear la instancia compartida y cablear router + `ChannelHandler`.
2. Correr la suite; si hay fugas de estado entre tests, agregar fixture de limpieza
   (p. ej. `conversation_service._repo` nuevo por test) sin debilitar aserciones.
3. Verificación manual opcional: crear sesión por REST y consultarla; simular webhook
   y verificar que `GET /api/v1/conversations/{id}` la ve.

**Pruebas / verificación**: pytest verde; sin regresiones en e2e.
**Riesgos**: estado compartido entre tests (mitigación en acciones); sigue siendo
memoria por proceso — con más de un worker de uvicorn el problema renace, la solución
definitiva es Postgres ("stage two" ya anunciado en el código). Esta fase solo elimina
la partición *dentro* del proceso.

🛑 **CHECKPOINT** — fin del plan.
**Commit sugerido**: `refactor(back): share conversation service across channels`
