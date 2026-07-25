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

## Desarrollo

- Cada paquete (`backend/`, `frontend/`) tiene su propio README con instrucciones detalladas.
- Las contribuciones se hacen vía pull request hacia `main`.
- **Trabajo con IA (Claude Code, Codex, gentle-ai)**: ver [README-IA.md](README-IA.md) — flujo homologado de planes por fases, reglas y setup por herramienta.
