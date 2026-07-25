# Plan — Postgres 17 local con Docker para pruebas · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-24 · **Tipo**: plan de implementación por fases.
> **Base**: [20260723-health-terceros-backend.plan.md](.claude/analysis/plans/20260723-health-terceros-backend.plan.md)
> (dejó el check activo de Postgres que esta BD local va a satisfacer). Contexto del
> brain: `Stack y arquitectura.md` — Postgres corre en Dokploy en la nube; la BD local
> debe **coincidir en versión mayor (17)** para "misma URL en dev y prod = cero bugs
> de doble motor".
> **Proyectos afectados**: backend (tooling de desarrollo; cero código de aplicación).
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

Levantar un **Postgres 17 local en Docker** con un comando, para agilizar pruebas
locales: hoy `DATABASE_URL` vacío significa que `POST /health/integrations/postgres`
responde 503 en local, y cuando llegue la persistencia real (Feature C: ingesta de
afiliados, conversaciones trazables) hará falta una BD local que no dependa de la
nube. Versión **17** para coincidir con el Postgres del Dokploy de producción.

## Contexto / hallazgos del análisis

- **Consumidores de `DATABASE_URL` hoy**: solo el health check
  ([database.py](backend/app/services/integrations/database.py) — `psycopg.connect` +
  `SELECT 1`, con `_normalize_dsn` que ya tolera el prefijo `postgresql+psycopg://`).
  No hay modelos ni repositorios con persistencia (los repos actuales son en memoria;
  la BD real entra con la Feature C del brain). **Por eso este plan es 100% tooling:
  cero código de aplicación.**
- **`psycopg[binary]>=3.2` ya es dependencia runtime**
  ([pyproject.toml:11](backend/pyproject.toml#L11)) — cero dependencias nuevas.
- **No existe ningún archivo Docker** en el repo (ni compose ni Dockerfile). Docker
  Desktop del usuario quedó operativo hoy (WSL/`WslService` arreglado; engine 29.6.1).
- **Los tests no tocan la BD** (mockean `psycopg.connect` —
  [test_integrations_health.py](backend/tests/test_integrations_health.py)): la suite
  seguirá verde con o sin el contenedor. La BD local es para pruebas manuales y para
  la Feature C.
- **Deploy no afectado**: en Dokploy el backend se construye con Nixpacks
  (build type configurado explícitamente por app, [README.md](README.md) sección
  Deploy) — un `docker-compose.yml` en la raíz es solo para desarrollo local y no
  cambia nada del deploy. Se documenta como dev-only.
- [dev.py](dev.py) — launcher simple con `verificar_prerequisitos()` + `lanzar()`
  (subprocess por proceso). Integrar el arranque de la BD ahí es posible pero
  opcional: no todo el mundo necesita la BD para trabajar (los repos son en memoria)
  y exigir Docker en `dev.py` sería un prerequisito nuevo para todos → se hace como
  fase opcional y **no bloqueante** (la BD se levanta solo si Docker está disponible,
  con aviso si no).
- `.env` real del usuario: `DATABASE_URL` está vacío — tras la Fase 1 el usuario lo
  apunta a la BD local (valor documentado en `.env.example`).

## Decisiones pendientes (bloqueantes)

(ninguna — resueltas en el análisis: imagen `postgres:17` estándar (la de Debian, la
misma familia que usa Dokploy; la variante alpine no aporta nada aquí), credenciales
dev-only documentadas, puerto estándar 5432 con chequeo de conflicto en pre-flight.)

## Principios

- **Cero código de aplicación**: solo tooling (`docker-compose.yml`), docs y
  `.env.example`. La suite no cambia (144 passed + 3 skipped se mantiene).
- Credenciales del compose = solo desarrollo local (van en el repo porque no protegen
  nada); las de la nube siguen viviendo únicamente en Dokploy/.env.
- Volumen con nombre para que los datos sobrevivan `docker compose down` (sin `-v`).
- Sin dependencias nuevas de Python; sin cambios al contrato front↔back.
- Aditivo puro.

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | backend | Ninguno | 5m | _(sin commit)_ |
| 1 | Compose con Postgres 17 + docs + `.env.example` | backend | Aditivo | 20m | `build: add local postgres 17 via docker compose` |
| 2 | _(opcional)_ `dev.py` levanta la BD si Docker está disponible | backend | Bajo | 15m | `feat(back): start local postgres from dev script` |

Total: ~40m (25m sin la fase opcional).

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: backend
**Objetivo**: confirmar que el entorno puede correr el contenedor.
**Archivos afectados**: ninguno.
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. `docker version` → engine respondiendo (quedó operativo hoy; si no, revisar
   `WslService` — episodio conocido).
2. Puerto 5432 libre: `netstat -ano | findstr :5432` → sin listeners (si hay un
   Postgres nativo instalado, decidir puerto alterno 5433 antes de la Fase 1).
3. Suite verde: desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` →
   144 passed + 3 skipped.
4. Confirmar que `POST /health/integrations/postgres` hoy responde 503 "no
   configurado" (estado esperado sin BD).

**Pruebas / verificación**: las de arriba.
**Riesgos**: puerto 5432 ocupado → se resuelve en el checkpoint eligiendo 5433.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit)_

---

## Fase 1 — Compose con Postgres 17 + docs + `.env.example`

**Proyecto**: backend (tooling en la raíz del monorepo)
**Objetivo**: `docker compose up -d db` levanta un Postgres 17 local persistente y el
health check del backend lo ve en verde.
**Archivos afectados**:
- `docker-compose.yml` — **nuevo, en la raíz**:
  ```yaml
  # BD local de desarrollo — NO se usa en deploy (Dokploy tiene su propio Postgres).
  services:
    db:
      image: postgres:17
      container_name: reto-innovacion-db
      environment:
        POSTGRES_USER: reto
        POSTGRES_PASSWORD: reto        # solo desarrollo local
        POSTGRES_DB: reto_innovacion
      ports:
        - "5432:5432"
      volumes:
        - reto_pgdata:/var/lib/postgresql/data
      healthcheck:
        test: ["CMD-SHELL", "pg_isready -U reto -d reto_innovacion"]
        interval: 5s
        timeout: 3s
        retries: 10
  volumes:
    reto_pgdata:
  ```
- [backend/.env.example](backend/.env.example) — bajo `DATABASE_URL=`, comentario con
  el valor para la BD local del compose:
  `postgresql://reto:reto@localhost:5432/reto_innovacion`.
- [README.md](README.md) — en la sección de desarrollo: bloque corto "Base de datos
  local" (`docker compose up -d db`, `docker compose down`, el volumen persiste;
  `docker compose down -v` la borra).

**Impacto en contrato API (front↔back)**: No (env var existente, solo cambia su valor
local).
**Acciones**:
1. Crear `docker-compose.yml` (arriba).
2. Actualizar `.env.example` y README.
3. Verificación manual completa (la hace el orquestador/usuario, los agentes no
   levantan contenedores): `docker compose up -d db` → `docker compose ps` healthy →
   usuario pone `DATABASE_URL=postgresql://reto:reto@localhost:5432/reto_innovacion`
   en su `.env` → levantar uvicorn → `curl -X POST
   http://localhost:8000/health/integrations/postgres` → **200 con latency_ms**.
4. Suite completa verde (no cambia: los tests mockean psycopg).

**Pruebas / verificación**: pytest verde (144+3); check activo de postgres → 200 con
la BD arriba; parar el contenedor y repetir el check → 503 (nunca 500) — ruta negativa
ya cubierta por tests con mock, se confirma en vivo.
**Riesgos**: si Dokploy en la nube quedó con otra major (confirmar 17 con tu
compañero al crear el servicio); conflicto de puerto si aparece un Postgres nativo →
cambiar el mapeo a `5433:5432` y ajustar la URL documentada.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `build: add local postgres 17 via docker compose`

---

## Fase 2 — _(opcional)_ `dev.py` levanta la BD si Docker está disponible

**Proyecto**: backend (script raíz)
**Objetivo**: `python dev.py` deja también la BD arriba cuando Docker está presente,
sin convertir Docker en prerequisito (quien no lo tenga sigue trabajando igual — los
repos son en memoria).
**Archivos afectados**:
- [dev.py](dev.py) — antes de lanzar backend/frontend: si `shutil.which("docker")` y
  el engine responde, ejecutar `docker compose up -d db` (con `--wait` si se quiere
  esperar el healthcheck) e informar; si no hay Docker, imprimir un aviso de una
  línea y continuar (no es error). `Ctrl+C` NO baja la BD (es barata y bajarla
  sorprende; se documenta `docker compose down` en README).

**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Función `levantar_db_local()` en `dev.py` con la lógica de arriba (usa el
   `shutil` ya importado; `subprocess.run` con timeout corto).
2. Probar los tres caminos: con Docker corriendo (BD sube), con Docker apagado
   (aviso y sigue), sin cambios cuando la BD ya estaba arriba (idempotente).

**Pruebas / verificación**: `python dev.py` en los tres escenarios; backend y
frontend levantan igual que antes; pytest no cambia.
**Riesgos**: `docker compose up` lento la primera vez (pull de la imagen ~150 MB) —
el aviso debe decir que está descargando; con `--wait` el arranque de dev.py se
retrasa hasta el healthy (aceptable, o lanzarlo sin `--wait`).

🛑 **CHECKPOINT** — fin del plan.
**Commit sugerido**: `feat(back): start local postgres from dev script`
