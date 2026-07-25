# AGENTS.md — Puente para agentes no-Claude (Codex, gentle-ai, Cursor, etc.)

> Este repo se gobierna desde `CLAUDE.md` y `.claude/`. Este archivo NO duplica esas
> reglas: te dice dónde están y cómo aplicarlas si tu herramienta no las carga sola.
> **La fuente de verdad es siempre `CLAUDE.md` y `.claude/`** — si este archivo
> contradijera algo de allí, ganan ellos.

## Paso 0 obligatorio — Lee las reglas reales

Antes de tocar código, lee COMPLETOS estos archivos y obedécelos como si fueran tu
system prompt:

1. [CLAUDE.md](CLAUDE.md) — reglas generales del monorepo (comandos, contrato
   HTTP front↔back, env vars, stack mínimo).
2. [backend/CLAUDE.md](backend/CLAUDE.md) — arquitectura del backend (FastAPI,
   capas `api → services → repositories → models`). Léelo antes de tocar `backend/`.
3. [frontend/CLAUDE.md](frontend/CLAUDE.md) — arquitectura del frontend (Vue 3,
   features, HTTP solo vía `shared/services/`). Léelo antes de tocar `frontend/`.
4. [.claude/rules/commit-standards.md](.claude/rules/commit-standards.md) —
   Conventional Commits obligatorio; un hook de git bloquea mensajes inválidos.
5. [.claude/README.md](.claude/README.md) — el flujo de trabajo multiagente del repo.

## Setup una sola vez (cada clon nuevo)

```bash
git config core.hooksPath .claude/git-hooks
```

Esto activa el hook `commit-msg` que fuerza Conventional Commits. Es independiente
de qué IA uses — instálalo siempre.

## El flujo del repo: plan → ejecución por fases

Este repo NO se trabaja con cambios ad-hoc grandes. El flujo es:

1. **Planear**: sigue las instrucciones de
   [.claude/commands/gen-plan.md](.claude/commands/gen-plan.md) al pie de la letra
   (son markdown plano: léelas y ejecútalas). Producen un plan por fases en
   `.claude/analysis/plans/YYYYMMDD-<slug>.plan.md`. Solo análisis — cero código.
2. **Ejecutar**: sigue [.claude/commands/run-plan.md](.claude/commands/run-plan.md)
   fase por fase, con la adaptación de roles de abajo.

Si el usuario te pide "gen-plan X" o "run-plan X" (con o sin `/`), eso significa
seguir el archivo de comando correspondiente.

### Adaptación si tu herramienta NO tiene subagentes (Codex, etc.)

`run-plan.md` delega en 3 subagentes definidos en `.claude/agents/`. Si no puedes
lanzar subagentes, **asume cada rol secuencialmente**, leyendo su archivo y
respetando sus restricciones como si fueran las tuyas:

| Rol | Definición | Restricciones duras que heredas |
|---|---|---|
| implementer | [.claude/agents/implementer.md](.claude/agents/implementer.md) | UNA tarea a la vez; escribe solo en backend: `app/`, `tests/`, `.env.example` · frontend: `src/`, `index.html`, `.env.example` |
| test-runner | [.claude/agents/test-runner.md](.claude/agents/test-runner.md) | solo ejecuta y reporta fiel (pytest / `npm run build`); JAMÁS arregla nada en este rol |
| debugger | [.claude/agents/debugger.md](.claude/agents/debugger.md) | fix mínimo, máx. 3 intentos; al 3.º fallido te detienes y escalas al usuario; prohibido debilitar tests |

Al cambiar de rol, anuncia el cambio ("[test-runner] ejecutando pytest…") para que
el checkpoint sea auditable igual que con subagentes reales.

### Guardarraíles innegociables (aplican a CUALQUIER IA)

- **Nunca ejecutes git** (add/commit/push/branch): cada fase cierra en un
  🛑 checkpoint donde muestras el diff y el commit sugerido; **el humano commitea**.
- **Nunca avances con la verificación en rojo** (pytest backend / build frontend).
- **Nunca instales dependencias** (pip/npm) sin aprobación explícita del usuario.
- **No toques**: `.claude/`, `dev.py`, ningún `CLAUDE.md`, este `AGENTS.md`,
  `pyproject.toml`, `package.json`.
- **Contrato front↔back sagrado**: si cambias rutas, shape del JSON, status codes o
  env vars (`VITE_API_URL` / `FRONTEND_URL`), decláralo en el checkpoint y nunca
  parches un solo lado a ciegas.
- Fases que tocan ambos proyectos: **backend primero**.

## Nota para usuarios de gentle-ai

gentle-ai configura tu agente a nivel global/workspace; está bien usarlo, pero
**dentro de este repo el flujo es el de `.claude/` descrito arriba**, no el SDD de
gentle-ai. No generes specs ni configuración de gentle-ai dentro del repo: los
planes viven en `.claude/analysis/plans/` con el formato de `gen-plan.md`.
