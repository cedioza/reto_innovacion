# Plan — Prefijo único `/api/v1` para todo el backend · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-25 · **Tipo**: plan de implementación por fases.
> **Base**: [20260723-health-terceros-backend.plan.md](.claude/analysis/plans/20260723-health-terceros-backend.plan.md)
> (creó `/health/integrations`),
> [20260725-a3-orquestador-conversacional-llm.plan.md](.claude/analysis/plans/20260725-a3-orquestador-conversacional-llm.plan.md)
> (creó `/api/v1/conversations/...`) y el plan D1 de Cristian
> (`20260725-d1-ui-base-chat-mensajeria.plan.md` — el front que va a fijar rutas en D2).
> Motivación externa: criterio de H1 (`https://<dominio>/api/v1/health`) y la opción
> recomendada de deploy "front y API bajo el mismo dominio" (cero CORS), que exige que
> TODO el backend cuelgue de un prefijo único para que el proxy enrute por path.
> **Proyectos afectados**: ambos (backend primero; frontend es 1 archivo).
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

Unificar TODAS las rutas del backend bajo **`/api/v1`**. Hoy conviven tres esquemas:

| Router | Hoy | Queda |
|---|---|---|
| health | `/health` | `/api/v1/health` |
| integrations | `/health/integrations[...]` | `/api/v1/health/integrations[...]` |
| conversations | `/api/v1/conversations[...]` | (igual — ya cumple) |
| webhooks | `/webhooks/...` | `/api/v1/webhooks/...` |

Hacerlo AHORA, antes de que D2 cablee el chat al backend: cada día de espera fija más
rutas viejas en el front. Es carril backend (tuyo), no el de Cristian.

## Contexto / hallazgos del análisis

- [main.py:22-25](backend/app/main.py#L22-L25) incluye los 4 routers planos — el
  cambio natural es un `APIRouter(prefix="/api/v1")` raíz que los agrupe, y recortar
  el prefijo propio de [conversations.py:18](backend/app/api/routes/conversations.py#L18)
  de `/api/v1/conversations` a `/conversations` (las rutas resultantes de
  conversations NO cambian → los tests de conversations/orquestador/e2e quedan
  intactos).
- [health.py](backend/app/api/routes/health.py) — `GET /health` sin prefijo; el
  docstring lo marca como liveness del deploy → el **health check path de Dokploy**
  documentado en [README.md](README.md) (sección Deploy) debe actualizarse a
  `/api/v1/health` (criterio H1 cumplido de paso).
- **Webhooks también se mueven** (decisión, ver abajo):
  [webhooks.py:16](backend/app/api/routes/webhooks.py#L16) pasa a colgar del raíz →
  `/api/v1/webhooks/...`. Además
  [telegram_client.py](backend/app/services/telegram_client.py) construye la URL
  pública del webhook (`{BACKEND_PUBLIC_URL}/webhooks/telegram`) → debe apuntar al
  path nuevo, y sus tests assertan esa URL.
- **Frontend (D1)**: [api.js](frontend/src/shared/services/api.js) ya existe como
  cliente base único (regla del front ✓) y su `getHealth()` llama **`/health`** — la
  única llamada real hoy; [useChat.js](frontend/src/features/chat/composables/useChat.js)
  es 100% mock (aún no llama la API). Por eso la ventana: solo hay UNA ruta que
  corregir en el front hoy; tras D2 serían varias.
- **Tests backend afectados** (rutas literales): `test_health.py`,
  `test_integrations_health.py`, `test_telegram_webhook.py`,
  `test_telegram_webhook_setup.py`, `test_whatsapp_webhook_verify.py`,
  `test_ycloud_webhooks.py`. Los de conversations no cambian.
- **Línea base**: master (`64fe3f2`, D1 mergeado) = 201 passed + 6 skipped y build
  del front OK (verificado hoy en la auditoría del merge). Si el PR de A5 se mergea
  antes de ejecutar este plan, la línea base pasa a 226 + 9 — el pre-flight registra
  la que encuentre.
- Sin dependencias nuevas, sin env vars nuevas.

**Decisiones resueltas en el análisis:**

1. **Webhooks bajo `/api/v1` también** — el objetivo es UN prefijo para que el proxy
   enrute por path; dejar `/webhooks` fuera obligaría a una segunda regla de proxy y
   rompe el criterio "todo el back cuelga de un prefijo". Costo operativo: cuando se
   registren los webhooks reales (Meta/YCloud/Telegram, al deployar) se usa el path
   nuevo — hoy no hay webhooks registrados en producción, así que el costo es cero si
   se hace ya. `set_telegram_webhook` se actualiza en la misma fase.
2. **Sin alias de compatibilidad** (`/health` viejo NO se conserva): no hay ningún
   consumidor en producción (el deploy de Dokploy está en montaje; el front se
   corrige en la Fase 2 del mismo plan). Aditivo-antes-que-destructivo cede ante
   "cero rutas fantasma" en un cambio de 30 minutos con todo el contrato bajo control.
3. **`api.js` mantiene `BASE_URL` = host** (de `VITE_API_URL`) y los **paths llevan
   `/api/v1` explícito** — así el path del front es idéntico al del backend
   (contrato legible) y en el escenario same-domain basta `VITE_API_URL=""`
   (rutas relativas). Alternativa descartada: meter `/api/v1` en BASE_URL (oculta el
   contrato y complica curls copiados).

## Decisiones pendientes (bloqueantes)

(ninguna — las 3 de diseño quedaron resueltas arriba. Coordinación humana: avisar a
Cristian del cambio de contrato ANTES de que arranque D2 — el checkpoint de la Fase 1
lo recuerda.)

## Principios

- Backend primero (Fase 1), frontend consume después (Fase 2) — cada fase deja verde
  su proyecto (pytest / `npm run build`).
- Contrato HTTP explícito: la tabla del Objetivo ES el cambio de contrato; nada más
  cambia (shapes, status codes y bodies intactos).
- Cambio mecánico: prohibido aprovechar para refactors colaterales.
- Cero dependencias, cero env vars nuevas.
- Los planes históricos en `.claude/analysis/plans/` NO se editan (mencionan rutas
  viejas: son registro).

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | ambos | Ninguno | 5m | _(sin commit)_ |
| 1 | Backend: todo bajo `/api/v1` (+tests, README, regla) | backend | Alto (contrato) | 25m | `refactor(back): unify all routes under api v1 prefix` |
| 2 | Frontend: `api.js` apunta a `/api/v1/health` | frontend | Bajo | 10m | `fix(front): point health call to api v1 prefix` |

Total: ~40m.

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: ambos
**Objetivo**: punto de partida verde en los dos proyectos.
**Archivos afectados**: ninguno.
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Backend desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` → registrar la
   línea base (201+6 si A5 no está mergeado; 226+9 si ya lo está).
2. Frontend desde `frontend/`: `npm run build` → OK.
3. Confirmar con `git log` si el PR de A5 ya está en master (contexto, no bloqueante:
   este plan no toca los archivos de A5).

**Pruebas / verificación**: las de arriba.
**Riesgos**: ninguno.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit)_

---

## Fase 1 — Backend: todo bajo `/api/v1`

**Proyecto**: backend
**Objetivo**: la tabla del Objetivo hecha realidad, con tests y docs alineados.
**Archivos afectados**:
- [main.py](backend/app/main.py) — router raíz:
  ```python
  api_v1 = APIRouter(prefix="/api/v1")
  api_v1.include_router(health_router)
  api_v1.include_router(integrations_router)
  api_v1.include_router(conversations_router)
  api_v1.include_router(webhooks_router)
  app.include_router(api_v1)
  ```
- [conversations.py:18](backend/app/api/routes/conversations.py#L18) — prefijo propio
  `/api/v1/conversations` → `/conversations` (rutas finales idénticas a hoy).
- [telegram_client.py](backend/app/services/telegram_client.py) — la URL del webhook
  registrado pasa a `{BACKEND_PUBLIC_URL}/api/v1/webhooks/telegram`.
- Tests (actualizar rutas literales, SIN debilitar aserciones): `test_health.py`,
  `test_integrations_health.py`, `test_telegram_webhook.py`,
  `test_telegram_webhook_setup.py` (incluye la URL de setWebhook),
  `test_whatsapp_webhook_verify.py`, `test_ycloud_webhooks.py`.
- Test nuevo pequeño (en `test_health.py`): `GET /health` (ruta vieja) → **404** —
  fija el contrato "sin alias" y evita regresiones de alguien re-registrando el
  router plano.
- [README.md](README.md) — sección Deploy: health check path → `/api/v1/health`;
  sección de webhooks (re-apuntar): paths con `/api/v1/webhooks/...`.
- [backend/CLAUDE.md](backend/CLAUDE.md) — una línea en Convenciones: "Todo endpoint
  HTTP cuelga de `/api/v1` (el router raíz de `main.py`); los routers declaran su
  prefijo SIN `/api/v1`."

**Impacto en contrato API (front↔back)**: **Sí — Alto.** Cambian las rutas de health,
integrations y webhooks (tabla del Objetivo); conversations NO cambia. Bodies, shapes
y status codes idénticos. **Quién actualiza el otro lado**: la Fase 2 (front, mismo
plan, misma sesión). **Externos**: los webhooks se registrarán con el path nuevo
(nada registrado aún en producción); el health check de Dokploy se configura con
`/api/v1/health`. ⚠️ Avisar a Cristian ANTES de que arranque D2.
**Acciones**:
1. Aplicar los cambios de rutas (arriba).
2. Actualizar los 6 archivos de tests + test nuevo de 404.
3. README + backend/CLAUDE.md.
4. Suite completa verde.

**Pruebas / verificación**: pytest verde (mismo conteo de la línea base + 1 del test
de 404); manual: levantar uvicorn → `curl http://localhost:8000/api/v1/health` → 200
`{"status":"ok"}`; `curl http://localhost:8000/health` → 404; ruta negativa ya
cubierta por los tests existentes (404/422/503 se conservan bajo el prefijo nuevo).
**Riesgos**: si el deploy de Dokploy ya quedó configurado con `/health` como health
check, actualizarlo al re-deployar (nota para Cristian); tests con rutas hardcodeadas
que se me escapen → el conteo de pytest los delata (por eso la suite completa es la
verificación).

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `refactor(back): unify all routes under api v1 prefix`

---

## Fase 2 — Frontend: `api.js` apunta a `/api/v1/health`

**Proyecto**: frontend
**Objetivo**: la única llamada real del front hoy (`getHealth()`) usa la ruta nueva;
convención documentada para D2.
**Archivos afectados**:
- [api.js](frontend/src/shared/services/api.js) — `getHealth()`: `/health` →
  `/api/v1/health`; comentario de una línea: "Convención: todos los paths llevan el
  prefijo `/api/v1` explícito (contrato del backend)".

**Impacto en contrato API (front↔back)**: Sí — consume la ruta nueva de la Fase 1
(este ES el lado que se actualiza).
**Acciones**:
1. Editar `api.js` (arriba).
2. `npm run build` OK.
3. Manual (API caída contemplada por diseño: `request()` ya lanza con
   `Error HTTP {status}` y quien la llame lo maneja): levantar backend + front y
   verificar en consola del navegador que `getHealth()` responde — o `curl` directo a
   la ruta desde el front dev server si no hay consumidor visual aún.

**Pruebas / verificación**: `npm run build` verde; el mock del chat (D1) no se toca.
**Riesgos**: ninguno (un path en un archivo).

🛑 **CHECKPOINT** — fin del plan.
**Commit sugerido**: `fix(front): point health call to api v1 prefix`
