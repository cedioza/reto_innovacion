# Plan — H1 (parcial): fallback de SPA para Dokploy + housekeeping git · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-25 · **Tipo**: plan de implementación por fases.
> **Base**: [20260725-e2-pagina-aseguradora-simulada.plan.md](.claude/analysis/plans/20260725-e2-pagina-aseguradora-simulada.plan.md)
> (creó `/aseguradora/{token}` — la ruta directa que el jurado abre desde el correo y
> que HOY se caería con 404 en un static server sin fallback) y la sección Deploy del
> [README.md](README.md#L46) (que ya documenta la asunción pendiente de verificar y
> su plan B: "cambiar el front a Dockerfile con nginx").
> Tarea del vault relacionada: H1 (Despliegue en Dokploy) — este plan cubre SOLO el
> fallback de SPA del frontend; el resto de H1 (apps, dominios, Postgres) es
> operación en el panel de Dokploy, no código.
> **Proyectos afectados**: frontend (+ una fase operativa de git, sin código).
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

1. Que las **rutas directas de la SPA** (`/aseguradora/{token}`, `/panel`) respondan
   `index.html` en el deploy de Dokploy en vez de 404 — con un **Dockerfile de nginx
   versionado en el repo** (control total, sin depender de si el modo Static de
   Dokploy hace fallback o no). Es el último eslabón para que el link del correo de
   E1/E2 funcione en producción.
2. Housekeeping git: remote apuntando a la casa real del repo
   (`cedioza/reto_innovacion` — GitHub avisa "repository moved" en cada push) y
   borrar la rama remota duplicada `plan/b1-catalogo-multiproducto-json`.

## Contexto / hallazgos del análisis

- **El front no tiene Dockerfile** — hoy: [package.json](frontend/package.json)
  (`npm run build` → `dist/`), [vite.config.js](frontend/vite.config.js), y el
  [README.md:52](README.md#L52) que documenta la asunción sin verificar: *"el modo
  Static sirve la SPA… si responde 404, cambiar el front a Dockerfile con nginx
  (`try_files $uri $uri/ /index.html;`)"*. Este plan ejecuta directamente ese plan B
  — es la única opción **verificable desde el repo** (el modo Static de Dokploy no
  es configurable por archivo versionado, y con E2 en producción ya no es aceptable
  "probar a ver si funciona" el domingo).
- **El router usa history mode**
  ([router/index.js:6](frontend/src/router/index.js#L6)) con 3 rutas: `/`, `/panel`,
  `/aseguradora/:token`. Sin fallback, cualquier refresh o apertura directa fuera de
  `/` da 404 del servidor estático.
- **`VITE_API_URL` es variable de BUILD** (no de runtime): el Dockerfile debe
  aceptarla como `ARG` y pasarla al `npm run build`. En el escenario recomendado
  "front y API bajo el mismo dominio" va **vacía** (paths relativos → cero CORS,
  criterio de DEC-007); si el front queda en subdominio propio, se pasa la URL del
  backend en la config de build de Dokploy.
- **El ruteo same-domain no va en nginx**: Traefik (el proxy de Dokploy) enruta por
  path — backend con regla `/api/v1` y front como catch-all del mismo dominio. El
  nginx del contenedor solo sirve la SPA (desacoplado del nombre del servicio del
  backend). Se documenta en el README.
- **Backend como precedente**: ya se despliega con artefacto versionado
  ([backend/Procfile](backend/Procfile), Nixpacks) — el front pasa a Dockerfile con
  la misma filosofía: el repo manda, el panel solo apunta.
- **Git**: `git remote -v` → `zubcarz/reto_innovacion` (cada push recibe el aviso
  "This repository moved… use git@github.com:cedioza/reto_innovacion.git"); ramas
  remotas `plan/164736-b1-...` (la integrada, del JSONL) y
  `plan/b1-catalogo-multiproducto-json` (duplicada, un push extra de la sesión
  paralela — commit equivalente `4ec76ee`, mismo contenido que `a460275` ya en
  master). Antes de borrar: verificar que no tenga commits únicos
  (`git log origin/plan/b1-... --not origin/master` debe listar solo el commit
  redundante del catálogo o nada).
- Docker Desktop local operativo (29.6.1, WSL arreglado hoy) → la Fase 1 es
  **verificable localmente** con `docker build` + `curl`, sin tocar el VPS.

## Decisiones pendientes (bloqueantes)

(ninguna técnica. Coordinación humana: quien opere el panel de Dokploy —
Cristian — debe cambiar el build type del front de Static a **Dockerfile** al
re-deployar; el checkpoint de la Fase 1 lo recuerda.)

## Principios

- El deploy se define en el repo (Dockerfile versionado), no en clics del panel.
- nginx mínimo: servir SPA con fallback + cache de assets; el ruteo de dominios es
  de Traefik/Dokploy y se documenta, no se hardcodea.
- Cero cambios de código de la app: `src/` no se toca; pytest y build siguen
  intactos.
- La fase operativa de git no lleva commit y cada comando destructivo se verifica
  antes (la rama duplicada solo se borra tras confirmar que no tiene commits únicos).

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | ambos | Ninguno | 5m | _(sin commit)_ |
| 1 | Dockerfile nginx del front con fallback SPA + README | frontend | Medio (deploy) | 30m | `build(front): add nginx dockerfile with spa fallback` |
| 2 | Housekeeping git: remote nuevo + borrar rama duplicada | — (operativa) | Ninguno en código | 10m | _(sin commit)_ |

Total: ~45m.

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: ambos
**Objetivo**: punto de partida verde + Docker disponible.
**Archivos afectados**: ninguno.
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Backend desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` → línea base
   esperada **285 passed + 9 skipped** (master con E2+D4).
2. Frontend desde `frontend/`: `npm run build` → OK.
3. `docker version` → daemon arriba (necesario para verificar la Fase 1 en local).

**Pruebas / verificación**: las de arriba.
**Riesgos**: ninguno.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit)_

---

## Fase 1 — Dockerfile nginx del front con fallback SPA + README

**Proyecto**: frontend
**Objetivo**: la SPA se sirve desde nginx con fallback a `index.html` — las rutas
directas (`/aseguradora/{token}`, `/panel`) funcionan en producción por diseño, no
por suerte.
**Archivos afectados**:
- `frontend/Dockerfile` (nuevo) — multi-stage:
  - stage build: `node:20-alpine`, `npm ci`, `ARG VITE_API_URL=""` →
    `ENV VITE_API_URL=$VITE_API_URL`, `npm run build`;
  - stage final: `nginx:alpine`, copia `dist/` a `/usr/share/nginx/html` y
    `nginx.conf` a `/etc/nginx/conf.d/default.conf`; `EXPOSE 80`.
- `frontend/nginx.conf` (nuevo) —
  - `location / { try_files $uri $uri/ /index.html; }` (el fallback — el corazón
    del plan);
  - `location /assets/ { expires 1y; add_header Cache-Control "public, immutable"; }`
    (los bundles de Vite van con hash en el nombre);
  - `index.html` sin cache agresiva (los deploys del sábado deben verse al
    refrescar).
- `frontend/.dockerignore` (nuevo) — `node_modules`, `dist`, `.env*` (que la imagen
  no arrastre secretos ni artefactos locales).
- [README.md](README.md#L46) — sección Deploy: el front pasa de "Static (asunción
  pendiente)" a **build type Dockerfile** (root `frontend/`, puerto del contenedor
  `80`, build arg `VITE_API_URL` — vacío en same-domain, URL del backend si
  subdominio); nota del ruteo same-domain vía Traefik (backend `/api/v1`, front
  catch-all); se elimina el párrafo de "Pendiente de verificar".

**Impacto en contrato API (front↔back)**: No (empaquetado del deploy; ninguna ruta
ni shape cambia). `VITE_API_URL` ya existía como contrato — solo se formaliza cómo
entra al build de producción.
**Acciones**:
1. Crear los 3 archivos.
2. Actualizar el README.
3. Verificación local con Docker (abajo).

**Pruebas / verificación**: desde `frontend/`:
`docker build -t reto-front-test .` →
`docker run -d --rm -p 8081:80 --name reto-front-test reto-front-test` →
- `curl -s -o /dev/null -w "%{http_code}" http://localhost:8081/` → **200**;
- `curl -s http://localhost:8081/aseguradora/token-cualquiera` → **200 con el HTML
  de la SPA** (el fallback en acción — hoy esto daría 404);
- `curl -s -o /dev/null -w "%{http_code}" http://localhost:8081/panel` → **200**;
- `curl -s -o /dev/null -w "%{http_code}" http://localhost:8081/assets/no-existe.js`
  → **404** (el fallback NO se traga los assets);
→ `docker stop reto-front-test`. Además `npm run build` normal sigue OK (nada del
dev flow cambia).
**Riesgos**: `npm ci` dentro del build necesita red (imagen base + registry) — es
el mismo requisito de cualquier build de Dokploy; el dev local (`py dev.py` con
Vite) no se ve afectado en absoluto.

🛑 **CHECKPOINT** — Detente aquí (⚠️ y avisa a Cristian: al re-deployar el front en
Dokploy, build type **Dockerfile**, root `frontend/`, puerto 80, build arg
`VITE_API_URL`). No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `build(front): add nginx dockerfile with spa fallback`

---

## Fase 2 — Housekeeping git: remote nuevo + borrar rama duplicada

**Proyecto**: — (operativa, sin código ni commit)
**Objetivo**: remote apuntando a la casa real del repo y cero ramas fantasma.
**Archivos afectados**: ninguno (solo config local de git y el remoto).
**Impacto en contrato API (front↔back)**: No.
**Acciones** (en orden, cada una verificada antes de la siguiente):
1. `git remote set-url origin git@github.com:cedioza/reto_innovacion.git` →
   verificar con `git remote -v` y `git fetch origin` (debe traer sin avisos de
   "repository moved"). El push por SSH sigue siendo con la llave de `zubcarz`
   (colaborador) — solo cambia la URL.
2. Verificar que la rama duplicada no tiene commits únicos:
   `git log --oneline origin/plan/b1-catalogo-multiproducto-json --not origin/master`
   → debe listar SOLO el commit redundante del catálogo (equivalente a `a460275` ya
   mergeado) o nada. Si apareciera algo más → ⛔ STOP y revisar con el usuario.
3. Borrarla: `git push origin --delete plan/b1-catalogo-multiproducto-json`.
4. (Opcional, preguntar al usuario en el checkpoint) Las ramas `plan/*` ya
   mergeadas e integradas (a1/a2/a3/a5, api-v1, d2, d3, 164736-b1, 164918-e1,
   183828-e2, 183805-d4, postgres-local-docker) también pueden borrarse del remoto
   — son registro histórico; borrarlas es cosmético, conservarlas es gratis.

**Pruebas / verificación**: `git remote -v` con la URL nueva; `git fetch origin` y
`git pull --ff-only origin master` limpios; `git branch -r` sin la duplicada;
un `git push` de prueba de una rama cualquiera ya NO muestra el aviso de "moved".
**Riesgos**: borrar una rama remota es irreversible sin reflog remoto — mitigado
por la verificación del paso 2 (no hay commits únicos) y porque el contenido ya
vive en master.

🛑 **CHECKPOINT** — fin del plan.
**Commit sugerido**: _(sin commit — operación de infraestructura git)_

---

## Deuda / fuera de alcance (anotada para el vault)

- El resto de **H1** es operación en el panel de Dokploy (crear las apps, dominios,
  HTTPS, Postgres, env vars, auto-deploy) — checklist de DEC-007, carril de quien
  opera el VPS.
- Si el equipo decide same-domain (recomendado): configurar en Dokploy el dominio
  del backend con path `/api/v1` y el front como raíz del mismo dominio, y build
  arg `VITE_API_URL` vacío. Si subdominios: `VITE_API_URL=https://api.<dominio>` y
  `FRONTEND_URL=https://<front>` en el backend (CORS).
- El health check del contenedor del front (nginx) puede apuntarse a `/` (200).
