# Reto Innovación 🚀

Monorepo del reto de innovación.

## Estructura

```
reto-innovacion/
├── backend/    # API en FastAPI (Python)
└── frontend/   # Aplicación web en Vue
```

## Backend

API construida con [FastAPI](https://fastapi.tiangolo.com/).

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate    # Windows
pip install -r requirements.txt
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
