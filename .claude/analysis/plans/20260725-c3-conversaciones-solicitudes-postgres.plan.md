# Plan — C3: Conversaciones y solicitudes persistidas en Postgres · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-25 · **Tipo**: plan de implementación por fases.
> **Base**: [20260724-postgres-local-docker.plan.md](.claude/analysis/plans/20260724-postgres-local-docker.plan.md)
> (dejó `docker-compose.yml` con Postgres 17 local y el health check activo),
> [20260723-health-terceros-backend.plan.md](.claude/analysis/plans/20260723-health-terceros-backend.plan.md)
> (check `SELECT 1` contra `DATABASE_URL`). Tarea del brain: **C3 — Conversaciones y
> solicitudes persistidas en Postgres** (Feature C, bloquea A4 y G1).
> **Proyectos afectados**: backend.
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

Las conversaciones (transcripción completa), las solicitudes con consentimiento y las
sesiones de canal (teléfono→conversación) dejan de vivir en dicts en memoria y pasan a
Postgres vía SQLModel, **manteniendo el contrato actual de los repositorios** (los
services no cambian de forma). El dedupe de eventos YCloud también pasa a BD. Con esto,
un redeploy ya no borra las ventas del panel: el jurado puede navegar el link días
después y la evidencia trazable sigue ahí.

## Contexto / hallazgos del análisis

**Los dos repos en memoria que hay que reemplazar:**

- [conversations.py](backend/app/repositories/conversations.py) — `ConversationRepository`:
  dict `session_id → ConversationResponse` con contrato `save / find / delete / count`.
  Lo que guarda es el **schema Pydantic completo** [ConversationResponse](backend/app/schemas/conversation.py#L78-L87)
  (estado, perfil, recomendación, cotización, aplicación y `messages` — la
  transcripción completa con rol, contenido, tipo y payload).
- [applications.py](backend/app/repositories/applications.py) — `ApplicationRepository`:
  dict `session_id → (evidence_hash, ConsentedApplication)` con contrato
  `save / find / get_evidence_hash / count / find_by_token` (búsqueda lineal por
  `handoff_token`).

**Consumidores (contrato a preservar):**

- [conversation.py:43](backend/app/services/conversation.py#L43) — `ConversationService`
  instancia su repo en `__init__`; **singleton de módulo** `conversation_service`
  ([conversation.py:319](backend/app/services/conversation.py#L319)) compartido por el
  router REST, el orquestador LLM y `ChannelHandler`.
- [consent.py:30](backend/app/services/consent.py#L30) — `ConsentService` idem, con
  singleton `consent_service` ([consent.py:137](backend/app/services/consent.py#L137))
  compartido por REST, `agent_tools._cerrar_venta` y el router de handoff.
- [orchestrator.py:438](backend/app/services/orchestrator.py#L438) — el orquestador
  muta la sesión y llama `conversation_service._repo.save(...)` directamente al final
  del turno. Todos los caminos de escritura terminan en un `save()` explícito, así que
  pasar de "mismo objeto mutable en memoria" a "copia deserializada de BD" es seguro.
- [test_shared_conversation_state.py](backend/tests/test_shared_conversation_state.py)
  — exige que REST y canales compartan estado; con BD detrás esto se cumple incluso
  con procesos separados, pero los singletons se mantienen.

**Los otros dos estados en memoria que la tarea manda a BD:**

- [channel_handler.py:76](backend/app/services/channel_handler.py#L76) —
  `ChannelHandler._sessions: dict[user_id → session_id]` (la "sesión de canal"
  teléfono→conversación). Si el backend se reinicia, el usuario de WhatsApp pierde el
  hilo y arranca de cero. `_pending_field` (línea 77) es estado efímero de UX y su
  pérdida es inocua (el `.get()` devuelve `None` y el flujo se recupera solo): se
  queda en memoria.
- [webhooks.py:18](backend/app/api/routes/webhooks.py#L18) —
  `_processed_ycloud_events: set[str]` con el comentario que ya anuncia esta tarea
  ("Postgres will provide cross-restart idempotency in stage two"). Ojo: vive en el
  **router**, y la regla de capas prohíbe que un router toque un repository → el
  dedupe debe exponerse vía service.

**Infraestructura ya lista (la tarea es puro modelo + repos):**

- `DATABASE_URL` ya existe en [Settings](backend/app/core/config.py#L16) y en
  [.env.example](backend/.env.example); [docker-compose.yml](docker-compose.yml)
  levanta Postgres 17 local (`postgresql://reto:reto@localhost:5432/reto_innovacion`);
  el health check [database.py](backend/app/services/integrations/database.py) pasa y
  ya tolera el esquema `postgresql+psycopg://`.
- [pyproject.toml](backend/pyproject.toml) trae `psycopg[binary]>=3.2` pero **no**
  SQLModel/SQLAlchemy → dependencia nueva `sqlmodel` (justificada: la pide la tarea).
- El venv corre **Python 3.14.2** — verificar en pre-flight que `sqlmodel` y su
  SQLAlchemy instalan y funcionan en 3.14 (SQLAlchemy ≥2.0.44 tiene wheels cp314).

**Decisión de diseño (persistencia):** guardar el documento Pydantic completo como
JSON (`model_dump(mode="json")` → columna JSONB en Postgres / JSON en SQLite) más
columnas indexables (`session_id` PK, `estado`, `canal`, timestamps;
`handoff_token` y `evidence_hash` como columnas propias en solicitudes para que
`find_by_token` sea un query y no un scan). Reconstrucción vía
`ConversationResponse.model_validate(...)`. Cero cambio de shape para los services.

**Tests existentes a adaptar (no borrar):**
[test_conversation_repository.py](backend/tests/test_conversation_repository.py) y
[test_applications_repository.py](backend/tests/test_applications_repository.py)
(mismos casos, contra engine SQLite in-memory);
[test_ycloud_webhooks.py](backend/tests/test_ycloud_webhooks.py) (dedupe);
[test_handoff_endpoint.py:119](backend/tests/test_handoff_endpoint.py#L119) tiene un
comentario que asume repos en memoria — revisarlo. El resto de la suite usa los
services de más arriba y no debería tocarse.

## Decisiones pendientes (bloqueantes)

(ninguna — resueltas en el análisis:)

- **Sin `DATABASE_URL` el backend cae a SQLite local** (`backend/app/data/local.db`):
  el flujo de desarrollo sin Docker sigue funcionando y la demo conserva persistencia
  igual. Postgres queda como el camino de deploy (Dokploy) y de pruebas locales con
  `docker compose up -d db`.
- **Tests contra SQLite in-memory** (engine inyectable por fixture, `StaticPool`),
  con nota de compatibilidad en el propio test — es lo que el criterio de aceptación
  de C3 permite ("o SQLite en CI con nota de compatibilidad"). Verificación manual
  E2E contra Postgres local en la Fase 5.
- **Sin Alembic**: `SQLModel.metadata.create_all` en el arranque (lifespan de
  FastAPI). Es hackathon; los modelos nuevos se crean solos y no hay migraciones de
  datos previos (hoy todo muere en memoria).
- **El engine y la sesión viven en `app/repositories/db.py`**: la regla de capas dice
  que repositories es el único lugar que conoce la persistencia; `main.py` solo llama
  `init_db()` en el lifespan (es entrypoint, no router).

## Principios

- Verde por fase: `.venv\Scripts\python.exe -m pytest -q` desde `backend/` al cierre
  de cada fase; el servidor levanta (`uvicorn app.main:app`).
- **Contrato de repos intacto**: los services no cambian de firma; el frontend no ve
  ninguna diferencia (cero impacto en el contrato HTTP).
- Aditivo antes que destructivo: primero modelos + engine (Fase 1), luego reemplazo
  repo por repo; los dicts solo desaparecen cuando su reemplazo está verde.
- Una sola dependencia nueva (`sqlmodel`), pedida explícitamente por la tarea.
- Config solo por env vars: se reusa `DATABASE_URL`; no se agregan variables nuevas.

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | backend | Ninguno | 10m | _(sin commit)_ |
| 1 | Dependencia, engine y modelos SQLModel | backend | Aditivo | 35m | `feat(back): add sqlmodel engine and persistence models` |
| 2 | `ConversationRepository` a BD | backend | Medio | 40m | `feat(back): persist conversations in postgres` |
| 3 | `ApplicationRepository` a BD | backend | Medio | 35m | `feat(back): persist consented applications in postgres` |
| 4 | Sesiones de canal y dedupe YCloud a BD | backend | Medio | 40m | `feat(back): persist channel sessions and ycloud dedupe` |
| 5 | Verificación E2E de persistencia + docs | backend | Ninguno | 20m | `docs(back): document postgres persistence for c3` |

Total estimado: ~3h (la estimación de C3 en el brain es 4h — hay margen).

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: backend
**Objetivo**: confirmar punto de partida verde y que el stack propuesto funciona en
este entorno antes de tocar nada.
**Archivos afectados**: ninguno (solo lectura / entorno).
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Suite verde: desde `backend/`, `.venv\Scripts\python.exe -m pytest -q`.
2. BD local arriba: `docker compose up -d db` desde la raíz y
   `GET /api/v1/health/integrations` (o el check de postgres) en verde con
   `DATABASE_URL=postgresql://reto:reto@localhost:5432/reto_innovacion` en
   `backend/.env`.
3. Compatibilidad Python 3.14: `.venv\Scripts\python.exe -m pip install --dry-run
   sqlmodel` y confirmar que resuelve SQLAlchemy con wheel cp314 (≥2.0.44). Si no
   resuelve, parar y reevaluar (riesgo señalado abajo).
4. Verificar que no hay callers de `count()` fuera de los tests (confirmado en
   análisis; re-chequear rápido con grep).
**Pruebas / verificación**: pytest verde; health de postgres ok; dry-run de pip sin
conflictos.
**Riesgos**: si `sqlmodel`/SQLAlchemy no soporta Python 3.14 en este venv, la
alternativa es fijar versiones recientes o usar SQLAlchemy puro (decisión a escalar
al usuario en el checkpoint).

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit — fase de solo lectura)_

---

## Fase 1 — Dependencia, engine y modelos SQLModel

**Proyecto**: backend
**Objetivo**: dejar la base de persistencia lista sin reemplazar todavía ningún repo:
dependencia, engine con fallback, los 4 modelos y `create_all` al arranque.
**Archivos afectados**:
[pyproject.toml](backend/pyproject.toml) ·
`backend/app/repositories/db.py` (nuevo) ·
`backend/app/models/conversation.py` (nuevo) ·
`backend/app/models/application.py` (nuevo) ·
`backend/app/models/channel.py` (nuevo) ·
[main.py](backend/app/main.py) ·
[.env.example](backend/.env.example) (solo comentario del fallback) ·
`backend/tests/test_db_models.py` (nuevo)
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Agregar `sqlmodel>=0.0.22` a `dependencies` en `pyproject.toml` e instalar en el
   venv (única dependencia nueva del plan).
2. Crear `app/repositories/db.py`: `get_engine()` (lazy, desde
   `settings.database_url`; si está vacía → SQLite `backend/app/data/local.db`),
   `init_db()` (`SQLModel.metadata.create_all`) y `get_session()` (context manager).
   Nada fuera de `repositories/` ejecuta queries.
3. Modelos SQLModel (`table=True`), documento JSON + columnas indexables:
   - `ConversationRecord` → tabla `conversaciones`: `session_id` (PK), `canal`,
     `estado`, `data` (JSON del `ConversationResponse` completo, historial incluido),
     `created_at`, `updated_at`.
   - `ApplicationRecord` → tabla `solicitudes`: `session_id` (PK), `evidence_hash`,
     `handoff_token` (indexado), `consent_timestamp`, `data` (JSON del
     `ConsentedApplication`), `created_at`.
   - `ChannelSessionRecord` → tabla `sesiones_canal`: `channel` + `user_ref` (PK
     compuesta), `session_id`, `updated_at`.
   - `ProcessedEventRecord` → tabla `eventos_procesados`: `event_id` (PK),
     `created_at`.
   Tipo JSON con variante JSONB en Postgres (`JSON().with_variant(JSONB, "postgresql")`).
4. Llamar `init_db()` desde un lifespan en `main.py` (los modelos se importan ahí
   para registrarse en la metadata).
5. Actualizar el comentario de `DATABASE_URL` en `.env.example`: vacía = SQLite local
   de desarrollo, con la URL del compose como valor recomendado.
6. Test nuevo `test_db_models.py`: `create_all` contra SQLite in-memory + roundtrip
   insert/select de cada tabla.
**Pruebas / verificación**: pytest verde (suite vieja intacta + test nuevo); `uvicorn
app.main:app` levanta y crea las tablas (verificar con `\dt` en psql o inspección
SQLite); health de postgres sigue ok.
**Riesgos**: `create_all` en import-time rompería los tests que importan `app.main` —
por eso va en lifespan, no a nivel de módulo.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `feat(back): add sqlmodel engine and persistence models`

---

## Fase 2 — `ConversationRepository` a BD

**Proyecto**: backend
**Objetivo**: la transcripción completa de cada conversación sobrevive reinicios; el
contrato `save / find / delete / count` no cambia.
**Archivos afectados**:
[conversations.py](backend/app/repositories/conversations.py) ·
[test_conversation_repository.py](backend/tests/test_conversation_repository.py)
**Impacto en contrato API (front↔back)**: No (persistencia interna; las rutas y el
shape JSON no cambian).
**Acciones**:
1. Reescribir `ConversationRepository` sobre `get_session()`: `save` hace upsert
   (`session.merge` o get+update) serializando con `model_dump(mode="json")`; `find`
   deserializa con `ConversationResponse.model_validate`; `delete` y `count` como
   queries. Acepta un `engine` opcional en `__init__` para inyección en tests.
2. Mantener las anotaciones del contrato actual (el repo recibe/devuelve el schema,
   nunca expone el modelo SQLModel fuera de la capa).
3. Adaptar `test_conversation_repository.py`: mismos 5 casos, fixture con engine
   SQLite in-memory (`StaticPool`) y nota de compatibilidad (criterio C3). Agregar un
   caso nuevo: guardar, **recrear el repo** (simula reinicio) y verificar que el
   historial completo (rol, contenido) sigue consultable.
4. Verificar los caminos de escritura compartidos: REST
   ([conversations.py router](backend/app/api/routes/conversations.py)), orquestador
   ([orchestrator.py:438](backend/app/services/orchestrator.py#L438) — su
   `_repo.save` directo sigue funcionando) y `ChannelHandler`. Correr la suite
   completa, en especial `test_conversation_service.py`, `test_orchestrator.py`,
   `test_e2e_orchestrator.py` y `test_shared_conversation_state.py`.
**Pruebas / verificación**: pytest verde; manual: crear conversación por REST,
reiniciar `uvicorn`, `GET /api/v1/conversations/{id}` la devuelve con sus mensajes.
Caso negativo: `GET` de sesión inexistente sigue en 404, nunca 500.
**Riesgos**: el repo en memoria devolvía el **mismo objeto mutable**; ahora `find`
devuelve una copia. Auditado: todos los flujos terminan en `save()` explícito, pero
si algún test dependía de identidad de objeto, se adapta el test (no el contrato).
Serialización: enums y floats pasan limpio con `mode="json"`.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 3 sin aprobación del usuario.
**Commit sugerido**: `feat(back): persist conversations in postgres`

---

## Fase 3 — `ApplicationRepository` a BD

**Proyecto**: backend
**Objetivo**: solicitudes con consentimiento (evidencia hash + timestamp) sobreviven
reinicios; `find_by_token` pasa de scan lineal a query indexado.
**Archivos afectados**:
[applications.py](backend/app/repositories/applications.py) ·
[test_applications_repository.py](backend/tests/test_applications_repository.py) ·
[test_handoff_endpoint.py](backend/tests/test_handoff_endpoint.py) (revisar el
comentario de la línea 119 que asume memoria)
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Reescribir `ApplicationRepository` sobre `get_session()` manteniendo
   `save(session_id, evidence_hash, application)` / `find` / `get_evidence_hash` /
   `count` / `find_by_token` (query por columna `handoff_token`).
2. Adaptar `test_applications_repository.py` (mismos casos + caso de reinicio, mismo
   patrón de fixture que la Fase 2) y agregar caso para `find_by_token` persistido.
3. Correr los flujos que dependen del repo: `test_consent.py`, `test_handoff*.py`,
   `test_agent_tools.py` (`_cerrar_venta` vía `consent_service`),
   `test_e2e_happy_path.py`. El handoff por token ahora sobrevive reinicios (el
   comentario de `test_handoff_endpoint.py:119` deja de ser cierto — actualizarlo y,
   si el caso ahora puede afirmarse positivo, fortalecer el test, nunca debilitarlo).
**Pruebas / verificación**: pytest verde; manual: flujo completo hasta consentimiento,
reiniciar backend, `GET /api/v1/handoff/{token}` sigue resolviendo la solicitud.
Negativo: token inexistente → 404.
**Riesgos**: `finalize_by_token` re-guarda con el `evidence_hash` original
([consent.py:127](backend/app/services/consent.py#L127)) — el upsert debe preservar
el hash, no recalcularlo.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 4 sin aprobación del usuario.
**Commit sugerido**: `feat(back): persist consented applications in postgres`

---

## Fase 4 — Sesiones de canal y dedupe YCloud a BD

**Proyecto**: backend
**Objetivo**: un usuario de WhatsApp no pierde su conversación cuando el backend se
reinicia, y un evento YCloud reintentado tras un redeploy no se procesa dos veces.
**Archivos afectados**:
`backend/app/repositories/channel_sessions.py` (nuevo) ·
[channel_handler.py](backend/app/services/channel_handler.py) ·
[webhooks.py](backend/app/api/routes/webhooks.py) ·
`backend/tests/test_channel_sessions_repository.py` (nuevo) ·
[test_ycloud_webhooks.py](backend/tests/test_ycloud_webhooks.py)
**Impacto en contrato API (front↔back)**: No (los webhooks son contrato con YCloud/
Telegram, y sus rutas/respuestas no cambian).
**Acciones**:
1. Nuevo `ChannelSessionRepository` (`find(channel, user_ref)` /
   `save(channel, user_ref, session_id)` / `mark_event_processed(event_id) -> bool` /
   `is_event_processed(event_id)`) sobre las tablas `sesiones_canal` y
   `eventos_procesados`. El dedupe usa insert + PK: si ya existe, devuelve `False`
   (idempotencia atómica, sin carrera check-then-set).
2. `ChannelHandler`: reemplazar `self._sessions` por el repo (el handler ya es un
   service, puede poseerlo — regla "cada service es dueño de UN repo"); `_pending_field`
   se queda en memoria (estado efímero de UX, pérdida inocua). Exponer
   `was_event_processed(event_id)` / `mark_event_processed(event_id)` en el handler
   para que el router no toque el repository (regla de capas).
3. [webhooks.py](backend/app/api/routes/webhooks.py): eliminar
   `_processed_ycloud_events` y su comentario; usar los métodos del handler. Mantener
   la semántica actual: el evento se marca procesado **solo después** de entregar la
   respuesta (líneas 131-136), para que un fallo de envío permita el retry.
4. Tests: nuevos casos de repo (sesión de canal sobrevive "reinicio"; evento marcado
   dos veces → segunda vez `False`); adaptar `test_ycloud_webhooks.py` al nuevo
   camino de dedupe.
**Pruebas / verificación**: pytest verde; manual (si hay canal configurado): conversar
por WhatsApp, reiniciar backend, el siguiente mensaje retoma la misma conversación.
Negativo: mismo `event_id` dos veces → una sola respuesta enviada.
**Riesgos**: `handle_incoming` corre en threadpool
([webhooks.py:131](backend/app/api/routes/webhooks.py#L131)) — cada operación abre su
propia sesión de BD, sin estado compartido mutable; el insert-por-PK evita la carrera
del set en memoria.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 5 sin aprobación del usuario.
**Commit sugerido**: `feat(back): persist channel sessions and ycloud dedupe`

---

## Fase 5 — Verificación E2E de persistencia + docs

**Proyecto**: backend
**Objetivo**: cerrar los criterios de aceptación de C3 con evidencia y dejar
documentado el modelo de persistencia.
**Archivos afectados**:
[backend/README.md](backend/README.md) (o CLAUDE.md del backend si aplica mejor) ·
ninguno de código salvo hallazgos.
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Contra Postgres local (`docker compose up -d db`): flujo completo por REST
   (crear → perfil → cotización → consentimiento) → **reiniciar uvicorn** →
   verificar que la conversación (`GET /conversations/{id}` con historial completo),
   la solicitud (`GET /handoff/{token}`) y la sesión de canal siguen ahí. Registrar
   el resultado en el checkpoint.
2. Suite completa verde por última vez + arranque limpio sin `DATABASE_URL` (fallback
   SQLite) para confirmar que el dev sin Docker no se rompe.
3. Documentar en el README del backend: tablas creadas, `create_all` al arranque (sin
   Alembic, decisión de hackathon), fallback SQLite y cómo apuntar a Postgres local.
**Pruebas / verificación**: checklist de criterios de C3 completo (flujo → reinicio →
datos vivos; historial consultable por conversación; tests de repos verdes contra
SQLite con nota de compatibilidad).
**Riesgos**: ninguno nuevo (fase de verificación y documentación).

🛑 **CHECKPOINT FINAL** — Revisión de cierre de C3 (marcar la tarea y desbloquear A4
y G1 en el brain).
**Commit sugerido**: `docs(back): document postgres persistence for c3`
