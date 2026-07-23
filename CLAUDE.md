# Reto Innovación — Monorepo

Monorepo de hackathon: `backend/` (FastAPI, Python 3.12+) y `frontend/` (Vue 3 + Vite).

## Comandos

```bash
python dev.py            # levanta backend (8000) y frontend (5173) a la vez
```

Por separado:

```bash
cd backend && .venv\Scripts\activate && uvicorn app.main:app --reload
cd frontend && npm run dev
```

Tests del backend: `cd backend && pytest`

## Reglas generales

- Cada proyecto tiene su propio `CLAUDE.md` con sus reglas de arquitectura: léelo antes de tocar código de ese proyecto.
- La configuración va en variables de entorno (`.env`, con su `.env.example` actualizado); nunca hardcodear URLs, puertos ni secretos.
- El contrato entre front y back es HTTP/JSON: el frontend solo conoce la API vía `VITE_API_URL`; el backend solo conoce al frontend vía `FRONTEND_URL` (CORS).
- No agregar dependencias sin necesidad clara; es un hackathon, mantener el stack mínimo.
