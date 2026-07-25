# Flujo paralelo de planes (worktrees)

Ejecuta hasta **3 planes ya generados** en simultáneo, cada uno en un git worktree
aislado con su propia rama, y luego intégralos a `master` en el orden en que se
lanzaron. **No modifica nada del flujo existente**: reutiliza los agentes de
[.claude/agents/](../agents/) como caja negra y convive con `/gen-plan` +
`/run-plan` (que siguen siendo el camino supervisado).

## Los dos comandos

```
# 1) Lanzar cada plan (desde 3 terminales/sesiones distintas, uno por sesión):
/launch-plan 20260725-b1-catalogo-multiproducto-json
/launch-plan 20260725-e1-handoff-correo-aseguradora-simulada
/launch-plan <otro-plan>

# 2) Cuando los lanzamientos terminen (status "pushed"), integrar:
/merge-plans plan/103015-b1-catalogo-multiproducto-json plan/103042-e1-handoff-...
```

- **`/launch-plan <path-o-slug>`** — valida el plan, crea
  `../worktrees/plan-<id>` + rama `plan/<id>` desde `origin/master`, ejecuta TODAS
  las fases sin gates (mismos agentes, mismo TDD-light, mismos guardarraíles),
  commitea por fase (Conventional Commits) y pushea la rama. Estado en el JSONL.
- **`/merge-plans <rama> <rama> [rama]`** — acepta 2 o 3 ramas; las ordena por
  `launched_at` del JSONL (ignora el orden de los argumentos), las mergea una por
  una contra master en `../worktrees/merge-integration`, resuelve conflictos con un
  subagente dedicado (corriendo la suite tras cada resolución), y con todo verde
  pushea a `master`. Si un conflicto no queda en verde: marca
  `needs_human_review` y se detiene sin propagar el merge roto.

## Formato del plan que espera `/launch-plan`

Exactamente el que produce `/gen-plan` (ver [gen-plan.md](../commands/gen-plan.md)):

- Archivo `.claude/analysis/plans/YYYYMMDD-<slug>.plan.md`, en español.
- Encabezado con `> **Fecha** / **Tipo** / **Base** / **Proyectos afectados**`.
- Secciones `## Objetivo`, `## Contexto`, `## Decisiones pendientes (bloqueantes)`,
  `## Principios`, `## Mapa de fases` (tabla) y una sección `## Fase N — ...` por
  fase con **Proyecto** (backend/frontend/ambos), **Acciones**,
  **Pruebas/verificación**, `🛑 CHECKPOINT` y **Commit sugerido** (Conventional
  Commits — ese mensaje es el que usa el commit de cada fase).
- ⚠️ Las **Decisiones pendientes deben estar resueltas** ("(ninguna)"): el modo
  autónomo no tiene gates para preguntarte a mitad de ejecución.

## Estado compartido — `.claude/state/plans-launched.jsonl`

Una línea JSON por lanzamiento (append/update SOLO vía
[plan-state.ps1](plan-state.ps1), que usa lock exclusivo + reintentos — a prueba de
3 sesiones concurrentes; el helper construye el JSON desde parámetros discretos,
nunca se le pasa JSON crudo por línea de comandos):

```json
{"id":"103015-b1-catalogo","branch":"plan/103015-b1-catalogo","plan_path":".claude/analysis/plans/20260725-b1-....plan.md","worktree":"C:/.../worktrees/plan-103015-b1-catalogo","launched_at":"2026-07-25T15:30:15.000Z","status":"running"}
```

Ciclo de estados: `running` → `pushed` → `merged`, con desvíos `failed`
(lanzamiento abortado; el worktree queda para inspección) y `needs_human_review`
(conflicto de merge sin resolver en verde). `launched_at` define el orden de
integración. El archivo NO se versiona (está en `.gitignore`).

## Layout de worktrees

```
c:\...\fork\
├── reto_innovacion\              ← repo principal (esta copia)
└── worktrees\
    ├── plan-<id>\                ← un worktree por lanzamiento (rama plan/<id>)
    └── merge-integration\        ← worktree temporal de /merge-plans
```

Cada worktree se bootstrapea solo: junction de `frontend/node_modules` al del repo
principal, pytest con el venv del principal por ruta absoluta, y copia de los
`.env` reales (todo eso está gitignorado y un worktree nuevo no lo trae).

## Consejos y límites

- **Máximo 3 `running`** a la vez (el comando lo valida contra el JSONL).
- El paralelismo real viene de invocar `/launch-plan` desde **sesiones distintas**
  (3 terminales). Una sola sesión ejecuta un lanzamiento a la vez.
- Lanza en paralelo planes de **ámbitos disjuntos** (p. ej. uno de catálogo, uno de
  consentimiento, uno de front): los conflictos de merge existen por diseño, pero
  menos solapamiento = integración más barata.
- Los agentes se cargan al inicio de sesión: estos comandos usan los agentes ya
  existentes, así que no requieren reinicio; el subagente de conflictos de
  `/merge-plans` es `general-purpose` (built-in) por la misma razón.
- Verificaciones manuales de los planes que gastan cuota de LLM en vivo se omiten
  durante el lanzamiento y quedan anotadas en el resumen para hacerlas después.
