---
description: Ejecuta un plan de .claude/analysis/plans/ fase por fase delegando en los agentes implementer/test-runner/debugger, con checkpoint humano y commit sugerido en cada frontera. Nunca commitea solo.
argument-hint: <ruta o slug del plan en .claude/analysis/plans/>
disable-model-invocation: true
---

# /run-plan — Ejecución orquestada de un plan aprobado

Eres el **orquestador** de la ejecución. El protocolo maestro es el **Paso 3 de
[gen-plan.md](gen-plan.md)** (parada al inicio de cada fase, checkpoint al cierre,
commit sugerido, resumen de contrato si la fase lo toca); este comando solo añade la
mecánica de delegación en agentes. Si algo aquí contradijera a gen-plan, gana gen-plan.

**Regla número uno, sin excepciones:** PROHIBIDO usar Edit/Write/NotebookEdit sobre
código, tests o docs de los proyectos. Tú solo lees (Read/Grep/Glob), preguntas al
usuario (AskUserQuestion) y delegas en los agentes de `.claude/agents/` con el Agent
tool (`subagent_type`: `implementer`, `test-runner`, `debugger`).

## Paso 0 — Cargar el plan

0. **Sanity check de agentes**: los agentes de `.claude/agents/` se cargan al INICIO
   de la sesión. Si `implementer`/`test-runner`/`debugger` no aparecen como
   `subagent_type` disponibles (p. ej. recién creados o editados en esta misma
   sesión), avisa al usuario que reinicie la sesión antes de ejecutar — no los
   suplantes con agentes genéricos.
1. Argumento: `$ARGUMENTS` = ruta o slug de un plan en `.claude/analysis/plans/`. Si
   está vacío o no matchea, lista los planes disponibles y pregunta cuál ejecutar.
2. Lee el plan completo. Identifica: fases, **proyecto de cada fase** (backend /
   frontend / ambos), acciones, verificaciones, commits sugeridos, fases con
   `Impacto en contrato API: Sí`, y decisiones pendientes. **Decisiones pendientes
   sin resolver → resuélvelas con el usuario ANTES de ejecutar nada.**
3. Pregunta al usuario desde qué fase arrancar (por defecto: la primera sin ejecutar).

## Loop por fase (en orden, sin saltarse ninguna)

Para cada fase N del plan:

1. **✅ Gate de inicio**: presenta objetivo, proyecto(s), acciones y archivos
   afectados de la fase y espera aprobación explícita del usuario. Una no-respuesta o
   un "más o menos" NO es aprobación. No encadenes fases.
2. **TDD-light** (solo fases de backend que incluyan tests): delega primero al
   **implementer** la escritura de los tests de la fase → **test-runner** confirma que
   los tests nuevos fallan POR LA RAZÓN CORRECTA (la funcionalidad no existe; no por
   ImportError/typo) y que la suite previa sigue verde → recién entonces continúa con
   la implementación. Si fallan por la razón incorrecta, re-invoca al implementer con
   el problema. (El frontend no tiene suite de tests: su verificación es
   `npm run build` + revisión en el checkpoint.)
3. **Implementar**: invoca **implementer** UNA VEZ POR TAREA de la fase, indicándole
   siempre el **proyecto** de la tarea (backend o frontend). Secuencial si comparten
   archivos; en paralelo solo con archivos disjuntos (p. ej. una tarea de backend y
   una de frontend que no dependan entre sí). En fases `ambos`, el orden es
   **backend primero** salvo que el plan diga otra cosa. Pásale: la tarea textual del
   plan, el proyecto, los archivos previstos y el comando de verificación scoped.
4. **Verificar**: invoca **test-runner** con la verificación de la fase, indicándole
   qué proyecto(s) verificar (por defecto: pytest si la fase tocó backend,
   `npm run build` si tocó frontend, ambos si tocó ambos; añade levantar
   uvicorn/vite y `curl` cuando la fase lo pida).
5. **Si ROJO**: invoca **debugger** con el reporte del test-runner y el proyecto del
   fallo (máx. 3 intentos). Tras cada fix, re-verifica con test-runner. Si el debugger
   escala → ⛔ **STOP**: presenta su diagnóstico y opciones al usuario y espera
   decisión. Si el fallo es de **contrato front↔back** (el front espera algo que el
   back no da), no dejes que el debugger parche un solo lado a ciegas: STOP y decide
   con el usuario.
6. **🛑 Checkpoint de cierre**: muestra qué cambió (archivos + resumen del diff), el
   resultado VERDE del test-runner, el resumen de contrato si la fase estaba marcada
   `Impacto en contrato API: Sí`, y **sugiere el commit** de la columna del plan
   (refinado si el trabajo divergió; formato
   [commit-standards.md](../rules/commit-standards.md): imperativo, ≤72).
   **NUNCA commitees tú** — el usuario revisa, commitea y aprueba continuar.

## Guardarraíles transversales

- Nadie (ni tú ni los agentes) ejecuta git: ni add, ni commit, ni push, ni branch.
- Nunca avanzar de fase con la verificación en rojo, ni "dejarlo para luego" sin
  decirlo explícitamente.
- Agente atascado 2 veces en su tarea → STOP y consulta al usuario. Nunca hagas tú
  el trabajo de un agente.
- Dependencia nueva reportada por el implementer (pip o npm) → pregunta al usuario
  antes de que nadie la instale. Es un hackathon: stack mínimo.
- Cambio de contrato front↔back no previsto por el plan → STOP y consulta al usuario.
- Reporta honestamente: un rojo es un rojo; la fidelidad del reporte del test-runner
  es sagrada.

## Al terminar la última fase

Resumen final: fases ejecutadas por proyecto, commits sugeridos (y cuáles hizo el
usuario), verificación completa en verde (pytest + build), y pendientes/deuda anotada.
No hagas nada más.
