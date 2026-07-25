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
principal y pytest con el venv del principal por ruta absoluta (todo eso está
gitignorado y un worktree nuevo no lo trae).

⚠️ **Regla de oro al borrar un worktree**: primero `cmd /c rmdir
"<wt>\frontend\node_modules"` (quita SOLO el enlace) y recién después
`git worktree remove <wt>`. Un borrado recursivo directo puede seguir la junction y
**vaciar el `node_modules` real del repo principal** (pasó el 25-jul-2026 y costó un
`npm ci`). Los hardlinks de `.env` no tienen este riesgo: borrar el nombre-enlace
nunca toca el contenido mientras exista el original.

## Secretos y `.env` en los worktrees

**Por defecto, los worktrees NO reciben ningún `.env`.** La suite completa del
backend (241 passed + 9 skipped, verificado sin `.env`) y el `npm run build` corren
sin secretos: los tests live están gateados por `RUN_LIVE_GEMINI_TESTS` (quedan
skipped) y `Settings` tiene defaults vacíos — los health checks degradan a "no
configurado" en vez de fallar. Menos copias de secretos en disco, cero secretos en
ramas/worktrees que se pushean.

Si un plan exige verificación en vivo (uvicorn contra Gemini/Postgres reales),
opciones en orden de preferencia:

1. **Hardlink temporal** (misma unidad, sin admin, sin segunda copia física; se
   retira al terminar): `cmd /c mklink /H "<wt>\backend\.env" "<main>\backend\.env"`
   y `del "<wt>\backend\.env"` después. Editar el original NO invalida el link.
2. **Variables de proceso** (nada toca el disco): setear solo las necesarias en la
   sesión que levanta uvicorn (`$env:GEMINI_API_KEY = ...`) — pydantic-settings lee
   el entorno real por encima del archivo.
3. **Copia explícita** (último recurso): `Copy-Item` del `.env` y borrado manual —
   es la opción con más residuo; evitarla.

Nunca: commitear un `.env` (gitignored en todos los worktrees, el `.gitignore` viaja
con el checkout), pasar secretos por argumentos de comandos (quedan en historial de
shell) o pegarlos en prompts de agentes.

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
