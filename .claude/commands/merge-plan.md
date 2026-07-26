# /merge-plan — Integración de UNA rama de plan a master (cupo rápido)

Eres el **orquestador de integración individual**. Recibes UNA rama `plan/<id>`
creada por `/launch-plan` que ya terminó (status `pushed`), la mergeas contra master
en un worktree de integración, verificas en verde y pusheas a `master`. Es el
complemento de `/merge-plans` (2-3 ramas) para cuando un lanzamiento paralelo
termina antes que los demás y quieres liberar el cupo y encadenar otro plan sobre
el master ya integrado.

## Paso 1 — Validar la rama

1. Argumento: `$ARGUMENTS` = UNA rama `plan/<id>` (acepta el `<id>` pelado). Más de
   una rama → usa `/merge-plans`. Vacío → error claro.
2. Lee el estado SIEMPRE con la ruta absoluta del repo principal:
   `powershell -NoProfile -File <main>\.claude\parallel\plan-state.ps1 -Action read`.
   La rama DEBE tener entrada en el JSONL:
   - `status: pushed` → OK, continúa.
   - `status: merged` → ya está integrada; repórtalo y termina sin hacer nada.
   - `status: failed` o `running` → ⛔ STOP y pregunta al usuario si de verdad
     quiere integrarla.
   - Sin entrada → ⛔ error claro y terminar.

## Paso 2 — Worktree de integración

Sea `<main>` el repo principal.

1. `git fetch origin` desde `<main>`.
2. Si `../worktrees/merge-integration` existe de una corrida anterior:
   primero `cmd /c rmdir "..\worktrees\merge-integration\frontend\node_modules"`
   (desenlazar la junction — NUNCA remover el worktree con ella viva), luego
   `git worktree remove ../worktrees/merge-integration --force` y borra su rama
   vieja `merge/...` con `git branch -D`.
3. Crear el worktree desde master remoto actualizado:
   ```
   git worktree add -b merge/<yyyyMMdd-HHmmss> ../worktrees/merge-integration origin/master
   ```
   Sea `<wt>` la ruta absoluta resultante.
4. Bootstrap (idéntico a `/launch-plan`): junction
   `cmd /c mklink /J "<wt>\frontend\node_modules" "<main>\frontend\node_modules"`;
   pytest siempre con `& "<main>\backend\.venv\Scripts\python.exe" -m pytest -q`
   (cwd `<wt>\backend`). **Sin `.env`** (los tests live quedan skipped — correcto).

## Paso 3 — Merge y verificación

1. Desde `<wt>`: `git merge origin/plan/<id>` (mensaje default "Merge ..." — el
   hook lo exime).
2. **Sin conflictos** → suite completa: pytest (conteo exacto) + `npm run build`
   desde `<wt>\frontend`.
3. **Con conflictos** (raro con una sola rama: solo si master avanzó tras el
   lanzamiento) → resolución agentica igual que `/merge-plans`: subagente
   **general-purpose** con los archivos en conflicto (rutas absolutas en `<wt>`),
   ambas intenciones (log de la rama + plan del JSONL) y la regla de oro de
   conservar la funcionalidad de ambos lados. El subagente SOLO edita; tú haces
   `git add -A` + `git commit`. Luego suite completa.
4. **Rojo** → itera con el mismo subagente (máx. 2 veces). Si sigue rojo:
   `plan-state.ps1 -Action update -Id <id> -Status needs_human_review -Reason "<motivo>"`,
   deja `<wt>` intacto y ⛔ STOP con reporte exacto.

## Paso 4 — Entrega a master

1. Verde → `git push origin HEAD:master` (desde `<wt>`).
2. Push rechazado (master avanzó) → `git fetch origin`, `git merge origin/master`
   en `<wt>` (resolviendo como el Paso 3 si hace falta), re-verifica en verde y
   reintenta UNA vez. Si vuelve a fallar → `needs_human_review` y STOP.

## Paso 5 — Cerrar estado y limpieza

1. `plan-state.ps1 -Action update -Id <id> -Status merged` (ruta absoluta de
   `<main>`).
2. Limpieza (solo con todo verde y pusheado). ⚠️ SIEMPRE la junction ANTES del
   worktree (incidente del 25-jul-2026: el borrado recursivo siguió el enlace y
   vació el `node_modules` real):
   ```
   cmd /c rmdir "<worktree>\frontend\node_modules"
   git worktree remove <worktree>
   ```
   Aplícalo al de integración Y al worktree `plan-<id>` de la rama mergeada. La
   rama remota queda como registro.
3. Recuerda al usuario: `git pull` en `<main>` (master avanzó) — y que el cupo de
   `/launch-plan` quedó libre para lanzar el siguiente plan sobre el master nuevo.
4. **Resumen final**: rama mergeada, conflictos (si hubo) y cómo se resolvieron,
   conteo exacto de la suite final, commit pusheado a master.

## Guardarraíles

- PROHIBIDO editar `.claude/` y los intocables del repo (`dev.py`, `CLAUDE.md`,
  `pyproject.toml`, `package.json`).
- El estado compartido SOLO vía `plan-state.ps1`, SIEMPRE por ruta absoluta del
  repo principal (la copia del worktree escribe un estado paralelo equivocado).
- Nunca `push --force`, nunca reescribir historia de master.
- Un rojo es un rojo: no se pushea a master con la suite fallando.
