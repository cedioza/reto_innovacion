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

- **Backend** — Application con build type **Nixpacks** (lee [backend/Procfile](backend/Procfile)); puerto del contenedor `8000`; health check path `/health`; env vars según [backend/.env.example](backend/.env.example) (`BACKEND_PUBLIC_URL` = dominio HTTPS asignado; `DATABASE_URL` = servicio Postgres creado en Dokploy). Tras el deploy, re-apuntar los webhooks de YCloud/Meta al dominio nuevo y re-registrar el de Telegram (`POST /webhooks/telegram/set`).
- **Frontend** — build type **Static**: build command `npm run build`, publish directory `dist`. ⚠️ `VITE_API_URL` se inyecta **en build time**: definirla en Environment antes de compilar (y rebuildar si cambia). Actualizar `FRONTEND_URL` del backend con el dominio del front (CORS).
- **Pendiente de verificar** (asunción: el modo Static sirve la SPA): abrir directo `https://<front>/panel` tras el primer deploy. El router usa history mode, así que el servidor debe hacer fallback a `index.html` en rutas sin archivo; si responde 404, cambiar el front a Dockerfile con nginx (`try_files $uri $uri/ /index.html;`).

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
