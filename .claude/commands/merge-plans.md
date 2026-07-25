# /merge-plans — Integración ordenada de ramas de planes paralelos a master

Eres el **orquestador de integración**. Recibes 2 o 3 ramas `plan/<id>` creadas por
`/launch-plan`, las mergeas UNA POR UNA contra master en un worktree de integración
— en el ORDEN en que fueron lanzadas (según el estado compartido, no según el orden
de los argumentos) — resolviendo conflictos con un subagente dedicado, y si todo
queda en verde, pusheas el resultado a `master`.

## Paso 1 — Ordenar por lanzamiento

1. Argumentos: `$ARGUMENTS` = 2 o 3 nombres de rama (formato `plan/<id>`; acepta
   también el `<id>` pelado). Menos de 2 o más de 3 → error claro.
2. Lee el estado: `powershell -NoProfile -File .claude/parallel/plan-state.ps1 -Action read`.
   Cada rama DEBE tener una entrada (idealmente `status: pushed`). Rama sin entrada
   en el JSONL → ⛔ error claro y terminar (no adivines el orden). Rama en estado
   `failed` o `running` → ⛔ STOP y pregunta al usuario si de verdad quiere
   integrarla.
3. Ordena las ramas por `launched_at` ascendente: **la primera lanzada se integra
   primero**. Anuncia el orden resuelto.

## Paso 2 — Worktree de integración

Sea `<main>` el repo principal.

1. `git fetch origin` desde `<main>`.
2. Si `../worktrees/merge-integration` existe de una corrida anterior:
   `git worktree remove ../worktrees/merge-integration --force` (su rama vieja
   `merge/...` puede borrarse con `git branch -D`).
3. Crear el worktree sobre una rama temporal de integración desde master remoto
   actualizado (master local suele estar checked-out en `<main>` — por eso la rama
   temporal):
   ```
   git worktree add -b merge/<yyyyMMdd-HHmmss> ../worktrees/merge-integration origin/master
   ```
   Sea `<wt>` la ruta absoluta resultante.
4. Bootstrap del entorno (idéntico a `/launch-plan`): junction
   `cmd /c mklink /J "<wt>\frontend\node_modules" "<main>\frontend\node_modules"`,
   pytest siempre con `& "<main>\backend\.venv\Scripts\python.exe" -m pytest -q`
   (cwd `<wt>\backend`). **Sin `.env`**: la suite y el build corren sin secretos
   (los tests live quedan skipped, que es lo correcto en integración).

## Paso 3 — Merges secuenciales (en el orden del Paso 1)

Para cada rama `<rama>`:

1. Desde `<wt>`: `git merge origin/<rama>` (mensaje default "Merge ..." — el hook lo
   exime).
2. **Sin conflictos** → verifica rápido (suite backend + build front); verde →
   siguiente rama. (Un merge limpio pero con tests rojos se trata igual que el punto
   4: interferencia semántica entre planes.)
3. **Con conflictos** → resolución agentica:
   - Recolecta: archivos en conflicto (`git status --porcelain`), el diff de cada
     lado (`git log --oneline origin/master..origin/<rama>`, `git diff` de los
     conflictos), y el `plan_path` de la rama según el JSONL (la intención escrita).
   - Lanza un subagente **general-purpose** (Agent tool — NO los agentes de
     feature-building) con: los archivos en conflicto (rutas absolutas en `<wt>`),
     ambas intenciones (mensajes de commit + resumen del plan de cada lado), y la
     instrucción de resolver **conservando la funcionalidad de AMBOS lados** (regla
     de oro: en código nuevo disjunto, mantener ambos; en colisiones reales, decidir
     por la intención de los planes y reportar qué eligió y por qué). El subagente
     SOLO edita archivos — nada de git.
   - Tú marcas la resolución: `git add -A` y `git commit` (mensaje "Merge ...").
   - Corre la suite completa (backend + build front desde `<wt>`).
4. **Tests rojos tras resolver** → dale al MISMO subagente el reporte del fallo para
   iterar (máx. **2 iteraciones**). Si sigue rojo:
   - `powershell -NoProfile -File .claude/parallel/plan-state.ps1 -Action update -Id <id de la rama> -Status needs_human_review -Reason "<qué conflicto/test falló>"`
   - ⛔ **DETENTE AQUÍ**: no mergees las ramas siguientes (no propagar un merge
     roto). Deja `<wt>` intacto para revisión humana y reporta el estado exacto
     (qué se integró, qué quedó pendiente, dónde está el conflicto).

## Paso 4 — Verificación final y entrega a master

Con TODAS las ramas mergeadas:

1. Suite completa una vez más desde `<wt>`: pytest (conteo exacto) + `npm run build`.
2. Verde → entrega directa a master (convención confirmada por el usuario para este
   flujo):
   ```
   git push origin HEAD:master        (desde <wt>)
   ```
   Si el push es rechazado (master avanzó mientras tanto): `git fetch origin`,
   `git merge origin/master` en `<wt>` (resolviendo igual que el Paso 3 si hiciera
   falta), re-verifica en verde y reintenta el push UNA vez. Si vuelve a fallar →
   `needs_human_review` y STOP.
3. Rojo → `needs_human_review` en la ÚLTIMA rama integrada (con motivo) y STOP.

## Paso 5 — Cerrar estado y resumen

1. Por cada rama integrada:
   `powershell -NoProfile -File .claude/parallel/plan-state.ps1 -Action update -Id <id> -Status merged`
2. Limpieza (solo si TODO quedó verde y pusheado). ⚠️ **SIEMPRE desenlazar la
   junction ANTES de remover un worktree** — el borrado recursivo puede seguirla y
   **vaciar el `node_modules` REAL del repo principal** (incidente ocurrido el
   25-jul-2026; costó un `npm ci`):
   ```
   cmd /c rmdir "<worktree>\frontend\node_modules"     ← quita SOLO el enlace
   git worktree remove <worktree>
   ```
   Aplícalo al de integración y a cada `plan-<id>` mergeado. Las ramas remotas
   quedan como registro — el usuario decide si borrarlas.
3. Recuerda al usuario actualizar su copia: `git pull` en `<main>` (master avanzó).
4. **Resumen final**: ramas mergeadas y en qué orden, cuántos conflictos hubo, en
   qué archivos y cómo se resolvió cada uno (una línea por conflicto), resultado
   exacto de la suite final, y el commit final pusheado a master.

## Guardarraíles

- PROHIBIDO editar `.claude/` (agentes, comandos, hooks) y los intocables del repo.
- El estado compartido SOLO se toca vía `plan-state.ps1`.
- Nunca `push --force`, nunca reescribir historia de master.
- Un rojo es un rojo: jamás continuar la cadena de merges con la suite fallando.
- El subagente de conflictos edita archivos; TODO git lo ejecutas tú desde `<wt>`.
