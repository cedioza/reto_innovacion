# Plan — B6: Prompt multicategoría con identificación de afiliado · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-26 · **Tipo**: plan de implementación por fases (micro-plan).
> **Base**: [20260725-b5-preguntas-por-categoria-matriz.plan.md](.claude/analysis/plans/20260725-b5-preguntas-por-categoria-matriz.plan.md)
> (dejó la regla 8 de fricción cero y las tools multicategoría — B6 cierra sus 2
> brechas de prompt detectadas por `/completar B5`),
> [20260725-a5-guardrails-y-confirmaciones.plan.md](.claude/analysis/plans/20260725-a5-guardrails-y-confirmaciones.plan.md)
> (los tests de la regla 6 asertan conceptos, no la frase de alcance). Tarea del
> brain: **B6 — Prompt multicategoría con identificación de afiliado** (sin
> dependencias; cerrar ANTES de grabar el video).
> **Proyectos afectados**: backend.
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

Cerrar las 2 brechas del system prompt que la verificación de B5 detectó: (1) el
saludo y la regla 6 siguen anclados a "seguros de hogar" mientras las tools, la
Matriz y el catálogo ya son de 5 categorías — "quiero asegurar mi carro" corre el
riesgo de tratarse como fuera de alcance en pleno demo de Movilidad; (2) el agente
nunca ofrece identificarse, así que la vía afiliado (fricción cero, el momento "no
te pregunto lo que ya sé") solo se activa si el cliente da su número espontáneamente.

## Contexto / hallazgos del análisis

- **Brecha 1 — anclaje a hogar** (verificado en el código actual, post-merges
  A4+B5): el saludo dice "acompañas a las personas a proteger su hogar"
  ([orchestrator.py:54-55](backend/app/services/orchestrator.py#L54-L55)) y la
  regla 6 dice "Tu alcance es acompañar la elección y compra de seguros de hogar"
  ([orchestrator.py:82](backend/app/services/orchestrator.py#L82)). Todo lo demás ya
  es multicategoría: la regla 8 (fricción cero por categoría), las 8 tools
  (`campos_pendientes` con enum de 5 categorías, `consultar_vehiculo`), el catálogo
  y el motor. La contradicción es real: la regla 6 instruye desviar lo que no sea
  hogar.
- **Brecha 2 — identificación**: ninguna parte del prompt sugiere preguntar si la
  persona es afiliada ni ofrecer identificarse. `perfilar_cliente` acepta
  `document_number` y resuelve la vía base con `source="base"` (B5), y la regla 8
  ya explica cómo usar lo conocido — falta solo la instrucción de ABRIR esa vía.
- **Tests que asertan texto del prompt** (los únicos dos, verificados):
  - [test_guardrails.py:403-415](backend/tests/test_guardrails.py#L403-L415) —
    asertan conceptos de las reglas 6-7 ("siniestros", "líneas de atención",
    "No improvises", "pide que te lo repita") que NO cambian con B6: la parte de
    siniestros/reclamos → líneas de atención se conserva tal cual.
  - [test_profiling_matrix.py:167-169](backend/tests/test_profiling_matrix.py#L167-L169)
    — aserta "campos_pendientes" in SYSTEM_PROMPT: intacto.
- **Cómo se testean los criterios**: el comportamiento real del LLM no se puede
  asertar con el mock guionado (el guion ES la respuesta del modelo). El patrón del
  repo para esto es doble: asserts de contenido del prompt (como
  `TestSystemPromptDomainRules`) + tests **live** gateados por env var
  (`test_orchestrator_live.py`, `test_guardrails_live.py` — los 9 skipped de la
  suite) que solo corren con key de Gemini. B6 sigue exactamente ese patrón.
- La cadena "seguros de hogar" solo existe en el SYSTEM_PROMPT dentro de
  `backend/app` (verificado con grep) — el cambio no toca services ni tools.

## Decisiones pendientes (bloqueantes)

(ninguna — resueltas en el análisis:)

- **Redacción del alcance**: el portafolio se enumera una sola vez en el saludo
  ("hogar, vida, accidentes personales, movilidad y crédito") y la regla 6 pasa a
  referirse a "los seguros del portafolio Colsubsidio"; el desvío de
  siniestros/reclamos/pagos/renovaciones se conserva palabra por palabra (los tests
  de guardrails lo asertan por concepto).
- **La identificación va como instrucción de apertura** (no regla dura numerada):
  párrafo tras las reglas — al inicio de la conversación preguntar con naturalidad
  si es afiliado y ofrecer el número ("si me das tu número de afiliado te ahorro
  preguntas"), UNA sola vez, sin insistir si no quiere — la vía declarada sigue
  completa (criterio de la Matriz).

## Principios

- Verde por fase: `.venv\Scripts\python.exe -m pytest -q` desde `backend/`.
- Cambio quirúrgico: SOLO el SYSTEM_PROMPT y tests — cero cambios en tools,
  services, schemas o contrato HTTP.
- Los tests live nuevos quedan gateados por env var como los existentes (skipped
  sin key — la suite CI no gasta cuota).

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | backend | Ninguno | 5m | _(sin commit)_ |
| 1 | Prompt multicategoría + oferta de identificación | backend | Aditivo | 35m | `feat(back): open prompt to full portfolio and affiliate id` |

Total estimado: ~40m (estimación del brain: 1h).

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: backend
**Objetivo**: baseline verde post-merges (A4+B5 acaban de entrar) y confirmación de
los anclajes.
**Archivos afectados**: ninguno (solo lectura).
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` (esperado: 519 passed,
   9 skipped).
2. Grep de `"seguros de hogar"` y `"proteger su hogar"` en `backend/app` y
   `backend/tests` — confirmar que solo el SYSTEM_PROMPT (y ningún test) ancla el
   alcance.
3. Confirmar el patrón de gating de los tests live (`test_orchestrator_live.py`:
   qué env var los activa) para replicarlo.
**Pruebas / verificación**: suite en verde; anclajes confirmados.
**Riesgos**: ninguno.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit — fase de solo lectura)_

---

## Fase 1 — Prompt multicategoría + oferta de identificación

**Proyecto**: backend
**Objetivo**: el agente atiende las 5 categorías sin contradicción de alcance y abre
la vía afiliado ofreciendo la identificación — los 2 criterios de B6.
**Archivos afectados**:
[orchestrator.py](backend/app/services/orchestrator.py) (solo `SYSTEM_PROMPT`) ·
`backend/tests/test_prompt_multicategoria.py` (nuevo) ·
[test_guardrails.py](backend/tests/test_guardrails.py) /
[test_profiling_matrix.py](backend/tests/test_profiling_matrix.py) (solo si algún
assert existente requiriera ajuste — según el análisis, ninguno)
**Impacto en contrato API (front↔back)**: No (texto del prompt; cero cambios de
rutas/shapes).
**Acciones**:
1. `SYSTEM_PROMPT` — tres ediciones:
   - Saludo (líneas 54-55): "acompañas a las personas a proteger lo que más les
     importa — su hogar, su vida, su familia, su vehículo y sus créditos…"
     (enumeración natural del portafolio de 5 categorías).
   - Regla 6 (línea 82): alcance = "la elección y compra de los seguros del
     portafolio Colsubsidio (hogar, vida, accidentes personales, movilidad y
     crédito)". El resto de la regla — siniestros, reclamos, pagos, renovaciones →
     líneas de atención, "No improvises procedimientos" — palabra por palabra igual.
   - Párrafo nuevo de apertura (junto al párrafo de enriquecer_perfil): al iniciar
     la conversación, preguntar con naturalidad si la persona es afiliada a
     Colsubsidio y ofrecerle identificarse con su número ("si me das tu número de
     afiliado te ahorro preguntas — no te pido lo que ya sabemos de ti"); UNA vez,
     sin insistir: si no quiere, seguir por la vía declarada con normalidad.
2. Tests (TDD-light) en `test_prompt_multicategoria.py`:
   - Prompt: menciona las 5 categorías (o sus nombres naturales) y NO contiene el
     alcance anclado ("Tu alcance es acompañar la elección y compra de seguros de
     hogar" desaparece; `"seguros de hogar"` ya no aparece como límite de alcance);
     conserva "siniestros" y "líneas de atención" (no romper guardrails).
   - Prompt: contiene la oferta de identificación ("afiliado" + "número" en el
     párrafo de apertura, y la instrucción de no insistir).
   - Guionado (mock, criterio 2 mecánico): conversación "quiero asegurar mi carro"
     → guion con `consultar_vehiculo` + `cotizar` de `movilidad-auto` termina con
     quote de movilidad no None (reusa el patrón de
     `test_runt_simulado.py::TestConversacionMovilidadGuionada` con otro arranque —
     valida que nada del código desvía movilidad).
   - **Live gateados** (mismo env var que `test_orchestrator_live.py`, skipped sin
     key): (a) primer turno de una conversación nueva → la respuesta real del
     modelo menciona la identificación de afiliado; (b) "quiero asegurar mi carro"
     → el modelo NO desvía por alcance (la respuesta no contiene la remisión a
     líneas de atención) y avanza el funnel. Son la evidencia real de los 2
     criterios; correr una vez antes de grabar el video.
3. Suite completa (los asserts de guardrails/matriz no deberían moverse).
**Pruebas / verificación**: pytest en verde (los live quedan skipped sin key);
manual recomendado ANTES del video: correr los 2 tests live con la key
(`$env:GEMINI_API_KEY=...; pytest tests\test_prompt_multicategoria.py -q -k live`)
— gasta ~2-4 requests de cuota.
**Riesgos**: cuota Gemini para los live (20 req/día por key — correrlos una sola
vez); si el modelo real no menciona la identificación en el primer turno, iterar la
redacción del párrafo (es prompt-engineering, no código — el checkpoint lo decide).

🛑 **CHECKPOINT FINAL** — B6 cumple sus 2 criterios (con evidencia live opcional
antes del video). Marcar B6 en el brain.
**Commit sugerido**: `feat(back): open prompt to full portfolio and affiliate id`
