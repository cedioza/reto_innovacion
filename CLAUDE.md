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
- **Commits:** Conventional Commits obligatorio — ver [.claude/rules/commit-standards.md](.claude/rules/commit-standards.md). El git hook `commit-msg` (`.claude/git-hooks/`, instalado con `git config core.hooksPath .claude/git-hooks`) bloquea mensajes que no cumplan.

## Flujo multiagente (`.claude/`)

Ver [.claude/README.md](.claude/README.md) para el detalle completo.

- **`/gen-plan <qué planear>`** — genera un plan de implementación por fases bajo `.claude/analysis/plans/` (solo análisis). Cada fase declara qué proyecto toca (`backend`, `frontend` o `ambos`) y si cambia el contrato HTTP entre front y back.
- **`/run-plan <plan>`** — ejecuta un plan delegando en los agentes de `.claude/agents/` (`implementer`, `test-runner`, `debugger`): orquestador sin permisos de escritura, TDD-light en fases de backend con tests, debugger con máx. 3 intentos, y checkpoint + commit sugerido en cada frontera de fase — nunca commitea solo. Par natural: `/gen-plan` planea → `/run-plan` ejecuta. Los agentes se cargan al inicio de sesión (si acabas de crearlos/editarlos, reinicia la sesión).
- **Regla de los agentes:** ámbito de escritura limitado (backend: `app|tests|.env.example`; frontend: `src|index.html|.env.example`); prohibido git, instalar dependencias y debilitar tests; en fases que toquen ambos proyectos, backend primero.
