# Reto Innovación 🚀

Monorepo del reto de innovación.

## Estructura

```
reto-innovacion/
├── backend/    # API en FastAPI (Python)
├── frontend/   # Aplicación web en Vue
└── dev.py      # levanta ambos proyectos a la vez
```

## Levantar todo de una vez

Con las dependencias ya instaladas (ver secciones de abajo):

```bash
python dev.py
```

Levanta el backend en `http://localhost:8000` y el frontend en `http://localhost:5173`; `Ctrl+C` detiene ambos.

## Backend

API construida con [FastAPI](https://fastapi.tiangolo.com/).

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate    # Windows
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

## Frontend

Aplicación web construida con [Vue](https://vuejs.org/).

```bash
cd frontend
npm install
npm run dev
```

## Deploy (Dokploy)

Ambos proyectos se despliegan en **Dokploy**:

- **Backend** — Application con build type **Nixpacks** (lee [backend/Procfile](backend/Procfile)); puerto del contenedor `8000`; health check path `/api/v1/health`; env vars según [backend/.env.example](backend/.env.example) (`BACKEND_PUBLIC_URL` = dominio HTTPS asignado; `DATABASE_URL` = servicio Postgres creado en Dokploy). Tras el deploy, re-apuntar los webhooks de YCloud/Meta al dominio nuevo y re-registrar el de Telegram (`POST /api/v1/webhooks/telegram/set`).
- **Frontend** — build type **Dockerfile** (lee [frontend/Dockerfile](frontend/Dockerfile), root `frontend/`); puerto del contenedor `80`; health check path `/`. El [frontend/nginx.conf](frontend/nginx.conf) hace el **fallback de SPA** (`try_files → index.html`), así las rutas directas (`/panel`, `/aseguradora/{token}` — el link del correo de handoff) funcionan al abrirse o refrescar. ⚠️ `VITE_API_URL` se inyecta **en build time** como *build arg* del Dockerfile (rebuildar si cambia).
- **Ruteo de dominios** (elige uno):
  - **Same-domain (recomendado, cero CORS)**: un solo dominio; en Dokploy, el backend con path `/api/v1` y el front como raíz. Build arg `VITE_API_URL` **vacío** (paths relativos).
  - **Subdominios**: `VITE_API_URL=https://api.<dominio>` en el build del front y `FRONTEND_URL=https://<front>` en el backend (CORS).

## Desarrollo

- Cada paquete (`backend/`, `frontend/`) tiene su propio README con instrucciones detalladas.
- Las contribuciones se hacen vía pull request hacia `master`.
- **Trabajo con IA (Claude Code, Codex, gentle-ai)**: ver [README-IA.md](README-IA.md) — flujo homologado de planes por fases, reglas y setup por herramienta.

### Base de datos local

Postgres 17 vía Docker Compose, igual versión que en la nube (Dokploy tiene su propio Postgres; esto es solo para desarrollo local):

```bash
docker compose up -d db
```

Configura en `backend/.env`:

```
DATABASE_URL=postgresql://reto:reto@localhost:5432/reto_innovacion
```

Para detenerla (los datos persisten en el volumen):

```bash
docker compose down
```

Para detenerla y borrar los datos:

```bash
docker compose down -v
```
