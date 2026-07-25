# Guía del flujo de IA homologado — Claude Code + Codex/gentle-ai

Este repo lo trabajamos dos personas con herramientas de IA distintas:

| Quién | Herramienta | Cómo carga las reglas |
|---|---|---|
| Carlos | Claude Code | Lee `CLAUDE.md` y `.claude/` de forma nativa |
| Compañero | Codex (GPT) + gentle-ai | Lee `AGENTS.md` (raíz y anidados) |

El objetivo de esta guía: que **ambas IAs sigan exactamente el mismo flujo, las
mismas reglas de arquitectura y los mismos guardarraíles**, sin importar cuál uses.

## La idea central: una sola fuente de verdad

Todas las reglas viven en `CLAUDE.md` y `.claude/`. Los `AGENTS.md` **no duplican
nada**: son puentes delgados que le dicen a Codex (o cualquier IA no-Claude)
"lee y obedece estos archivos". Así no hay dos versiones de las reglas que se
desincronicen.

```
CLAUDE.md                  ← reglas generales del monorepo      ┐
backend/CLAUDE.md          ← arquitectura backend (FastAPI)     │ fuente de verdad
frontend/CLAUDE.md         ← arquitectura frontend (Vue 3)      │ (la lee Claude
.claude/commands/          ← gen-plan.md y run-plan.md          │  directamente)
.claude/agents/            ← implementer, test-runner, debugger │
.claude/rules/             ← estándar de commits                ┘
        ▲
        │ "lee y obedece esto"
AGENTS.md                  ← puente raíz (flujo + guardarraíles)  ┐ los lee Codex/
backend/AGENTS.md          ← puente → backend/CLAUDE.md           │ gentle-ai
frontend/AGENTS.md         ← puente → frontend/CLAUDE.md          ┘ automáticamente
```

**Regla de mantenimiento**: si cambias una regla del proyecto, cámbiala en el
`CLAUDE.md` (o `.claude/`) correspondiente. Los `AGENTS.md` solo se tocan si
cambia la *estructura* del puente, no el contenido de las reglas.

## Setup del compañero (una sola vez)

1. **Instalar el hook de commits** (obligatorio, en cada clon nuevo):

   ```bash
   git config core.hooksPath .claude/git-hooks
   ```

   Fuerza [Conventional Commits](.claude/rules/commit-standards.md); un mensaje
   inválido bloquea el commit. Es independiente de la IA.

2. **Crear los slash commands en Codex** (opcional pero recomendado). Codex no
   lee comandos del repo; son config personal en tu máquina:

   `~/.codex/prompts/gen-plan.md`:

   ```markdown
   Lee .claude/commands/gen-plan.md de este repositorio y sigue sus
   instrucciones al pie de la letra. Argumentos: $ARGUMENTS
   ```

   `~/.codex/prompts/run-plan.md`:

   ```markdown
   Lee .claude/commands/run-plan.md de este repositorio y sigue sus
   instrucciones al pie de la letra. Argumentos: $ARGUMENTS
   ```

   Sin estos archivos también funciona: escribe "gen-plan tal cosa" en el chat y
   el `AGENTS.md` ya le dice a la IA qué significa.

3. **Si usas gentle-ai**: úsalo tranquilo como configurador global, pero dentro
   de este repo manda el flujo de `.claude/` — no generes specs SDD ni
   configuración de gentle-ai dentro del repo. Los planes viven en
   `.claude/analysis/plans/` con el formato de `gen-plan.md`.

## El flujo de trabajo (idéntico para ambos)

Nada de cambios grandes ad-hoc. Todo pasa por dos comandos en par:

### 1. `/gen-plan <qué construir>` — planear

Analiza el repo y genera un plan por fases en
`.claude/analysis/plans/YYYYMMDD-<slug>.plan.md`. **Solo análisis, cero código.**
Cada fase declara:

- Qué **proyecto** toca: `backend`, `frontend` o `ambos` (backend primero).
- Si tiene **impacto en el contrato API** front↔back (rutas, shape del JSON,
  status codes, env vars).
- Su **commit sugerido** en Conventional Commits.

### 2. `/run-plan <plan>` — ejecutar fase por fase

Por cada fase del plan:

```
✅ Gate de inicio   → la IA presenta la fase y ESPERA tu aprobación
[TDD-light]         → (backend con tests) primero los tests, se confirma que
                      fallan por la razón correcta
implementer         → implementa UNA tarea a la vez
test-runner         → pytest (backend) / npm run build (frontend) — VERDE o ROJO
[si ROJO] debugger  → fix mínimo, máx. 3 intentos; al 3.º escala y decides tú
🛑 Checkpoint       → diff + verificación en verde + commit sugerido
                      → TÚ revisas y TÚ commiteas. La IA jamás commitea.
```

### Diferencia entre herramientas: los subagentes

- **Claude Code** lanza `implementer`, `test-runner` y `debugger` como subagentes
  reales (definidos en [.claude/agents/](.claude/agents/)).
- **Codex no tiene subagentes**: la IA asume cada rol secuencialmente, leyendo el
  mismo archivo de definición y heredando sus restricciones (ámbito de escritura,
  máx. 3 intentos, test-runner que solo reporta y jamás arregla). Debe anunciar
  el rol activo ("[test-runner] ejecutando pytest…") para que el checkpoint sea
  auditable igual.

El resultado observable es el mismo: mismas fases, mismos checkpoints, mismo
formato de plan y de commits.

## Guardarraíles (aplican a cualquier IA, sin excepción)

- La IA **nunca ejecuta git** (add/commit/push/branch). El humano commitea en
  cada checkpoint tras revisar el diff.
- **Nunca se avanza de fase en rojo** (pytest backend / build frontend).
- **Dependencias nuevas** (pip/npm) siempre las aprueba el humano — hackathon,
  stack mínimo.
- Intocables para la IA: `.claude/`, `dev.py`, todos los `CLAUDE.md`, los
  `AGENTS.md`, `pyproject.toml`, `package.json`.
- **Contrato front↔back sagrado**: el frontend solo conoce la API vía
  `VITE_API_URL`; el backend solo conoce al frontend vía `FRONTEND_URL` (CORS).
  Un fallo de contrato nunca se parcha de un solo lado a ciegas.
- Ámbitos de escritura de la IA — backend: `app/`, `tests/`, `.env.example`;
  frontend: `src/`, `index.html`, `.env.example`.

## Qué esperar (y qué no)

Las reglas garantizan que ambas IAs produzcan **el mismo proceso**: planes con el
mismo formato, fases con checkpoints, commits válidos y arquitectura respetada.
No garantizan código *idéntico* — GPT y Claude escriben distinto. El punto de
convergencia es el **checkpoint humano de cada fase**: ahí es donde los dos
igualamos criterios revisando el diff antes de commitear.

## Referencias

- [.claude/README.md](.claude/README.md) — detalle completo de la orquestación.
- [.claude/commands/gen-plan.md](.claude/commands/gen-plan.md) — cómo se genera un plan.
- [.claude/commands/run-plan.md](.claude/commands/run-plan.md) — cómo se ejecuta.
- [.claude/rules/commit-standards.md](.claude/rules/commit-standards.md) — estándar de commits.
- [AGENTS.md](AGENTS.md) — el puente que lee Codex/gentle-ai.
