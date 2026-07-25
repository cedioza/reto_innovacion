# backend/AGENTS.md

Las reglas de arquitectura de este proyecto están en [CLAUDE.md](CLAUDE.md)
(mismo directorio): capas obligatorias `api → services → repositories → models`,
convenciones de FastAPI, tests con pytest. **Léelo completo y obedécelo** antes de
tocar cualquier archivo de `backend/`.

Reglas del monorepo y flujo de trabajo: [../AGENTS.md](../AGENTS.md).

Ámbito de escritura permitido aquí: `app/`, `tests/`, `.env.example`.
Verificación: desde `backend/`, `.venv\Scripts\python.exe -m pytest -q` (Windows)
o `.venv/bin/python -m pytest -q` (Unix).
