# /launch-plan — Ejecución autónoma de un plan YA generado, en un worktree aislado

Eres el **orquestador de lanzamiento paralelo**. Tomas un plan que YA existe en
`.claude/analysis/plans/` (generado por `/gen-plan`) y lo ejecutas de punta a punta
en un **git worktree aislado**, delegando cada tarea en los agentes existentes de
`.claude/agents/` (`implementer`, `test-runner`, `debugger`) **como caja negra** —
jamás los editas ni los suplantas. Hasta 3 lanzamientos pueden correr en paralelo
(uno por sesión/terminal).

Diferencias con `/run-plan` (que sigue existiendo intacto para el flujo supervisado):

| | `/run-plan` | `/launch-plan` |
|---|---|---|
| Gates por fase | usuario aprueba cada fase | **sin gates** — corre hasta el final |
| Commits | los hace el usuario | **los hace el orquestador** (Conventional Commits) |
| Dónde trabaja | el repo principal | un **worktree** en `../worktrees/plan-<id>` |
| Push | lo hace el usuario | `git push origin plan/<id>` al terminar en verde |

**Reglas heredadas que NO cambian**: los agentes no ejecutan git ni instalan
dependencias; TDD-light en fases backend con tests; nunca avanzar de fase en rojo;
debugger máx. 3 intentos; fidelidad total del reporte del test-runner.

## Paso 1 — Validar el plan y las precondiciones

1. Argumento: `$ARGUMENTS` = ruta o slug de un plan en `.claude/analysis/plans/`
   (con o sin fecha/extensión). Resuélvelo a un archivo `.plan.md` existente y
   légelo COMPLETO. Si no existe o no matchea exactamente uno → **error claro y
   terminar sin crear nada** (lista los planes disponibles).
2. Si el plan tiene **Decisiones pendientes (bloqueantes)** sin resolver → ⛔ STOP:
   este modo no tiene gates para resolverlas a mitad de camino. Pide al usuario
   resolverlas (o usar `/run-plan`) y termina.
3. **Cupo de paralelismo**: lee el estado con
   `powershell -NoProfile -File .claude/parallel/plan-state.ps1 -Action read` y
   cuenta las entradas con `"status":"running"`. Si ya hay **3** → error claro y
   terminar (esperar a que una termine o marcarla `failed` a mano).
4. Si el MISMO plan ya tiene una entrada `running` → ⛔ STOP (no lanzar dos veces el
   mismo plan en paralelo).

## Paso 2 — Crear el worktree aislado

Sea `<main>` la ruta absoluta del repo principal y `<slug>` el nombre del archivo
del plan sin fecha ni `.plan.md`.

1. `git fetch origin` (desde `<main>`).
2. Id de ejecución: `<id>` = `<HHmmss>-<slug>` (hora local de lanzamiento — único
   entre lanzamientos simultáneos; el timestamp completo va en el estado).
3. Crear worktree + rama en un solo paso, desde master actualizado:
   ```
   git worktree add -b plan/<id> ../worktrees/plan-<id> origin/master
   ```
   Sea `<wt>` la ruta absoluta resultante. Si la carpeta o la rama ya existieran
   (colisión rarísima de id) → agrega un sufijo `-2` y reintenta una vez.
4. **Bootstrap del entorno del worktree** (un worktree nuevo NO trae lo gitignorado):
   - `node_modules` por junction (instantáneo, sin admin):
     `cmd /c mklink /J "<wt>\frontend\node_modules" "<main>\frontend\node_modules"`
   - Backend: NO copiar el venv — todos los pytest se corren con el intérprete del
     repo principal por ruta absoluta, con cwd en el worktree:
     `& "<main>\backend\.venv\Scripts\python.exe" -m pytest -q` (desde `<wt>\backend`).
   - **`.env`: NO copiar por defecto.** La suite completa y el build corren SIN
     secretos (verificado: 241+9 sin `.env` — los tests live están gateados por env
     var y `Settings` tiene defaults vacíos). Menos copias de secretos en disco =
     menos superficie. Solo si el plan exige una verificación en vivo con servicios
     reales, crea un **hardlink** (misma unidad, sin admin, sin segunda copia
     física): `cmd /c mklink /H "<wt>\backend\.env" "<main>\backend\.env"` — y
     bórralo al terminar esa verificación.
   - Si el archivo del plan está **untracked** en `<main>` (aún sin commitear),
     cópialo a la misma ruta dentro de `<wt>` y haz ahí el primer commit:
     `docs(plan): add <slug> plan`.
5. Verifica el hook de commits: `git config core.hooksPath` debe decir
   `.claude/git-hooks` (config local compartida por los worktrees). Si no está,
   configúrala en `<main>` antes de commitear.

## Paso 3 — Registrar el lanzamiento (estado compartido, con lock)

Append de una línea al JSONL vía el helper (NUNCA escribas el archivo directo; el
helper construye el JSON y fija `launched_at` UTC y `status=running` él mismo):

```
powershell -NoProfile -File .claude/parallel/plan-state.ps1 -Action append -Id <id> -Branch plan/<id> -PlanPath <ruta relativa del plan> -Worktree <wt>
```

El `launched_at` que fija el helper define el ORDEN de integración de `/merge-plans`.

⚠️ Invoca el helper SIEMPRE por la **ruta absoluta del repo principal** (el worktree
tiene su propia copia del script que escribiría un estado paralelo equivocado si el
cwd quedó dentro del worktree — incidente del 25-jul-2026).

## Paso 4 — Ejecutar el plan (loop de fases, sin gates)

Sigue el protocolo de fases del flujo existente (el Paso 3 de
[gen-plan.md](gen-plan.md) y el loop de [run-plan.md](run-plan.md)), con estas
adaptaciones de modo autónomo:

1. **Sin gate de inicio ni checkpoint interactivo**: anuncia la fase (una línea) y
   ejecútala. Las fases se corren TODAS, en orden, sin saltarse ninguna.
2. **Rutas absolutas del worktree en cada prompt de agente**: los agentes trabajan
   como caja negra sobre los archivos que les indiques — todo path que les pases
   debe apuntar dentro de `<wt>`, y el comando de verificación que les des es el del
   bootstrap (pytest con el venv de `<main>` y cwd en `<wt>\backend`;
   `npm run build` desde `<wt>\frontend`). Nunca les pidas git.
3. **TDD-light** igual que siempre en fases backend con tests (tests → rojo por la
   razón correcta vía test-runner → implementación → verde).
4. **Verificación por fase** con test-runner; **si ROJO** → debugger (máx. 3
   intentos). Si escala al 3.º, o aparece una decisión que solo el usuario puede
   tomar, o un cambio de contrato no previsto por el plan → **aborto limpio**: ve al
   Paso 6 con `failed`.
5. **Commit al cierre de cada fase** (lo haces tú, el orquestador, desde `<wt>`):
   el mensaje sugerido por el plan (Conventional Commits, imperativo, ≤72 — el hook
   `commit-msg` lo valida). ⚠️ En PowerShell 5.1 no pongas comillas dobles dentro
   del mensaje (rompen el paso de args a git); usa here-string `@'...'@`.
6. **Sin verificaciones manuales en vivo**: las acciones de plan tipo "levantar
   uvicorn y curl" se ejecutan solo si no requieren criterio humano; las que gastan
   cuota de LLM en vivo se OMITEN (anótalas en el resumen como pendientes de
   verificación manual). La suite automatizada es la compuerta.

## Paso 5 — Push

Con todas las fases en verde (suite completa del backend + build del frontend como
verificación final desde `<wt>`):

```
git push origin plan/<id>       (desde <wt>)
```

## Paso 6 — Cerrar el estado y reportar

- Éxito → `powershell -NoProfile -File .claude/parallel/plan-state.ps1 -Action update -Id <id> -Status pushed`
- Fallo → `... -Status failed -Reason "<motivo corto>"` — NO pushees, NO borres el
  worktree (queda para inspección humana) y reporta el diagnóstico completo.

Resumen final: plan ejecutado, fases completadas, commits creados (hash + mensaje),
verificación final (conteos exactos), rama pusheada, worktree, y pendientes anotados
(verificaciones manuales omitidas). Recuerda al usuario integrar con
`/merge-plans plan/<id> [otras ramas...]` cuando los 2-3 lanzamientos terminen.

## Guardarraíles

- PROHIBIDO editar `.claude/` (agentes, comandos, hooks), `dev.py`, `CLAUDE.md`,
  `pyproject.toml`, `package.json` — ni aquí ni vía agentes.
- Todo git lo ejecuta el orquestador y SOLO dentro de `<wt>` (excepto `fetch` y
  `worktree add` desde `<main>`). Jamás `push` a master desde este comando.
- El estado compartido SOLO se toca vía `plan-state.ps1` (lock anti-carreras).
- Si algo del bootstrap falla (junction, .env, venv inexistente) → aborto limpio con
  `failed` ANTES de invocar ningún agente.
