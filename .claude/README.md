# Orquestación multiagente — Reto Innovación

Flujo mínimo de orquestación para ejecutar implementaciones por fases en el monorepo
(backend FastAPI + frontend Vue 3), con aprobación humana en cada frontera. Dos
comandos que trabajan en par y un roster de 3 agentes con mínimo privilegio.

> Adaptado de la infraestructura del take-home MincaAI (`2-build-test`), que era solo
> backend. Aquí cada fase del plan declara qué proyecto toca (`backend`, `frontend` o
> `ambos`) y los agentes conocen las reglas de arquitectura de ambos proyectos
> ([backend/CLAUDE.md](../backend/CLAUDE.md), [frontend/CLAUDE.md](../frontend/CLAUDE.md)).
> Los hooks de logging de SUBMISSION del original se descartaron; solo se conservó la
> gobernanza de commits.

## El par de comandos

| Comando | Rol | Escribe |
|---|---|---|
| `/gen-plan <qué planear>` | Analiza el repo y genera un plan por fases en `.claude/analysis/plans/` | solo el plan (`.plan.md`) |
| `/run-plan <plan>` | Ejecuta ese plan delegando en los agentes, fase por fase | nada |

**Nadie commitea salvo el usuario**: cada fase cierra en un 🛑 checkpoint con el
commit sugerido (formato [commit-standards.md](rules/commit-standards.md)); tú
revisas el diff y commiteas.

## Ejemplo de llamado

```
# 1. Planear (solo análisis, no toca código):
/gen-plan endpoint de mensajes en el backend y vista de chat que lo consume

# → genera .claude/analysis/plans/20260723-mensajes-y-chat.plan.md

# 2. Ejecutar el plan (sesión nueva si los agentes son recién creados):
/run-plan 20260723-mensajes-y-chat
```

Lo que ocurre dentro de `/run-plan` para cada fase del plan:

```
✅ Gate de inicio      → te presenta objetivo/proyecto/acciones y espera tu aprobación
[TDD-light]            → (fases backend con tests) implementer escribe los tests
                       → test-runner confirma que fallan POR LA RAZÓN CORRECTA
implementer            → una invocación por tarea, con el proyecto indicado
test-runner            → pytest (backend) y/o npm run build (frontend) — VERDE/ROJO
[si ROJO] debugger     → fix mínimo, máx. 3 intentos; al 3.º escala y TÚ decides
🛑 Checkpoint          → diff + verificación en verde + commit sugerido; commiteas tú
```

Los agentes los invoca el orquestador con el Agent tool (`subagent_type`); no se
llaman a mano. Si quisieras uno suelto, p. ej. solo verificar:

```
Lanza el agente test-runner con su batería por defecto sobre backend y frontend
```

## Roster de agentes (`.claude/agents/`)

| Agente | Modelo | Herramientas | Escribe en | Regla dura |
|---|---|---|---|---|
| [implementer](agents/implementer.md) | sonnet | Read, Grep, Glob, Write, Edit, Bash(pytest/build) | backend: `app\|tests\|.env.example` · frontend: `src\|index.html\|.env.example` | UNA tarea por invocación; sin git ni instalar dependencias |
| [test-runner](agents/test-runner.md) | haiku | Read, Glob, Bash(pytest/build) | nada | ejecuta y reporta fiel; jamás arregla |
| [debugger](agents/debugger.md) | sonnet | Read, Grep, Glob, Edit, Bash(pytest/build) | mismo ámbito que implementer | máx. 3 intentos → escalada; prohibido debilitar tests |

Los ámbitos de escritura se imponen por instrucción (el frontmatter restringe
herramientas, no rutas) y se verifican en el diff de cada checkpoint.

## Guardarraíles

- **Contrato front↔back sagrado**: el frontend solo conoce la API vía `VITE_API_URL`;
  el backend solo conoce al frontend vía `FRONTEND_URL` (CORS). Una fase que cambie
  rutas, shape del JSON o status codes va marcada `Impacto en contrato API: Sí` y
  dice en qué fase se actualiza el otro lado. Un fallo de contrato NUNCA se parcha de
  un solo lado a ciegas.
- **Nunca avanzar en rojo**, nunca "dejarlo para luego" sin decirlo.
- Agente atascado 2 veces / debugger escalado → STOP, decide el usuario.
- **Dependencias nuevas** (pip o npm) siempre las aprueba el usuario — es un
  hackathon, stack mínimo.
- Intocables para todos los agentes: `.claude/`, `dev.py`, `CLAUDE.md` (todos),
  `pyproject.toml`, `package.json`, todo comando git.

## Gobernanza de commits

- Conventional Commits obligatorio — ver [rules/commit-standards.md](rules/commit-standards.md).
- Se fuerza con el git hook [git-hooks/commit-msg](git-hooks/commit-msg), instalado con:
  ```
  git config core.hooksPath .claude/git-hooks
  ```
  (config local: cada clon nuevo debe volver a correrlo).

## Flujo paralelo (worktrees) — `/launch-plan` + `/merge-plans`

Segundo modo de ejecución, para correr **hasta 3 planes ya generados en simultáneo**
sin tocar el flujo supervisado (detalle completo en
[parallel/README.md](parallel/README.md)). Reutiliza los MISMOS agentes como caja
negra; lo que cambia es quién aprueba y dónde se trabaja:

| | Supervisado (`/run-plan`) | Paralelo (`/launch-plan`) |
|---|---|---|
| Gates por fase | tú apruebas cada fase | sin gates — corre de punta a punta |
| Commits | los haces tú | los hace el orquestador (Conventional Commits) |
| Dónde | el repo principal | worktree aislado `../worktrees/plan-<id>` |
| Integración | PR manual a master | `/merge-plans` (orden de lanzamiento) → master |
| Paralelismo | 1 plan a la vez | hasta 3 (una sesión/terminal por plan) |

```
FLUJO SUPERVISADO (existente)              FLUJO PARALELO (nuevo)
─────────────────────────────              ───────────────────────────────────────────
/gen-plan ──► plan.md                      /gen-plan ──► plan-A.md  plan-B.md  plan-C.md
    │                                            │            │          │
    ▼                                       (3 sesiones)      │          │
/run-plan (repo principal)                 /launch-plan A  /launch-plan B  /launch-plan C
    │                                            │            │          │
  ┌─fase──────────────────┐                 worktree A     worktree B   worktree C
  │ ✅ gate (tú apruebas) │                 rama plan/A    rama plan/B  rama plan/C
  │ implementer/test-     │                      │            │          │
  │ runner/debugger       │                  mismas fases, mismos agentes, sin gates
  │ 🛑 checkpoint         │                  commit por fase + push origin plan/<id>
  │   (tú commiteas)      │                      │            │          │
  └───────────────────────┘                      └────────────┼──────────┘
    │  ...fase N                                              ▼
    ▼                                        /merge-plans A B C   (ordena por
  PR manual ──► master                           │                 launched_at del JSONL)
                                             merge secuencial en worktree de
                                             integración; conflictos → subagente
                                             + suite verde │ rojo → STOP
                                                 │
                                             push ──► master
```

Estado compartido: `.claude/state/plans-launched.jsonl` (una línea por lanzamiento,
escrita solo vía [parallel/plan-state.ps1](parallel/plan-state.ps1) con lock — su
`launched_at` define el orden de integración). Ciclo:
`running → pushed → merged`, con desvíos `failed` y `needs_human_review`.

**Cuándo usar cuál**: `/run-plan` cuando quieres revisar cada fase (cambios de
contrato, decisiones finas); `/launch-plan` para planes autocontenidos, sin
decisiones pendientes y de ámbitos disjuntos entre sí (menos conflictos al mergear).

**Los worktrees verifican SIN secretos**: la suite del backend y el build del front
corren sin `.env` (los tests live quedan skipped por diseño — verificado 241+9). Los
`.env` reales nunca se copian a los worktrees por defecto; si un plan exige
verificación en vivo, se enlaza el del repo principal por hardlink y se retira al
terminar.

## Notas operativas

- Los agentes se cargan al **inicio de sesión**: si acabas de crearlos o editarlos,
  reinicia la sesión antes de `/run-plan` (el comando lo verifica en su paso 0).
