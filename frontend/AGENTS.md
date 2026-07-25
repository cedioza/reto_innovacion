# frontend/AGENTS.md

Las reglas de arquitectura de este proyecto están en [CLAUDE.md](CLAUDE.md)
(mismo directorio): arquitectura por features, HTTP solo vía `shared/services/`
(cliente base `api.js`), env vars `VITE_*`. **Léelo completo y obedécelo** antes de
tocar cualquier archivo de `frontend/`.

Reglas del monorepo y flujo de trabajo: [../AGENTS.md](../AGENTS.md).

Ámbito de escritura permitido aquí: `src/`, `index.html`, `.env.example`.
Verificación: desde `frontend/`, `npm run build`.
