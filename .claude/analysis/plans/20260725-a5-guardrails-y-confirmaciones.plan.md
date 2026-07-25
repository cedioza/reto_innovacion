# Plan — A5: Guardrails y confirmaciones · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-25 · **Tipo**: plan de implementación por fases.
> **Base**: [20260725-a3-orquestador-conversacional-llm.plan.md](.claude/analysis/plans/20260725-a3-orquestador-conversacional-llm.plan.md)
> (ejecutado — orquestador con loop de tools, system prompt con reglas duras y
> verificación live completa) y
> [20260724-a2-contrato-herramientas-agente.plan.md](.claude/analysis/plans/20260724-a2-contrato-herramientas-agente.plan.md)
> (las tools cuyos outputs son la única fuente de cifras). Insumo externo: tarea
> **A5** del brain y sus relaciones (`Stack y arquitectura` — principio 1;
> `Riesgos y supuestos` — R3 alucinaciones; `06 - Pitch/Preguntas del jurado` —
> "¿y si la IA promete una cobertura que no existe?").
> **Proyectos afectados**: backend.
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

Blindar al agente contra los tres modos de fallo que el jurado va a atacar:

1. **Nunca inventa precios ni coberturas** — hoy es una regla del prompt (esperanza);
   pasa a ser un **guard mecánico post-respuesta**: cualquier cifra monetaria del
   texto del asistente que no exista en los outputs de las tools se intercepta y se
   reemplaza por una respuesta segura con los datos reales del motor.
2. **Confirma lo entendido de un audio antes de actuar** — regla de confianza de voz
   del brain, forzada por construcción (no por prompt).
3. **Maneja con gracia el fuera de dominio** (siniestros, pagos, reclamos) y el
   "no entendí", explicando el alcance.

Es la respuesta ensayada a la pregunta más peligrosa del jurado. A5 depende de A3
(verde) y no bloquea a nadie: puro valor defensivo para la final.

## Contexto / hallazgos del análisis

**Estado del orquestador** ([orchestrator.py](backend/app/services/orchestrator.py),
línea base **201 passed + 6 skipped**):

- El `SYSTEM_PROMPT` (L38-61) ya tiene 5 reglas duras (precios solo de tools, 1-2
  preguntas, razones del motor, consentimiento, corregir rumbo) — A5 **agrega** las
  reglas de dominio y voz, no las reescribe.
- El texto final del turno se asigna en un único punto
  ([orchestrator.py:210-215](backend/app/services/orchestrator.py#L210-L215)) — el
  guard de precios se inserta ahí, entre el `reply.text` y el append a la sesión:
  un solo choke point, cero cambios en el loop.
- `ctx.quote` (dict del motor) está disponible en ese punto con
  `monthly_premium`, `annual_premium`, `base_amount` y `adjustments` — el **conjunto
  de cifras permitidas** se construye de ahí (más las variantes de formato).
- `respond(session_id, content)` recibe solo texto; `gemini_client.audio_part()`
  (A1, Fase 3) ya sabe construir la part multimodal pero **nadie la usa en el flujo
  conversacional** — la puerta de audio a nivel service es de esta tarea; la
  ingesta HTTP/webhook del audio es de las Features D/F (fuera de alcance).
- Los tests guionados de A3 ([test_orchestrator.py](backend/tests/test_orchestrator.py),
  [test_e2e_orchestrator.py](backend/tests/test_e2e_orchestrator.py)) dan el patrón
  exacto para las "conversaciones sintéticas" del criterio 3 de A5.

**Del vault**: `Preguntas del jurado` tiene la pregunta textual con su respuesta
preparada ("precios y coberturas salen solo del catálogo vía herramientas") — A5 la
convierte de argumento a **demo verificable**; `Alcance MVP` confirma que
siniestros/renovaciones están fuera del enunciado (por eso el fuera-de-dominio se
responde con alcance, no con features).

**Decisiones de diseño resueltas:**

1. **Guard de precios — solo patrones monetarios** para evitar falsos positivos
   (edades "35 años", estratos, rangos "26-40" NO deben dispararlo): regex sobre
   `$X`, `X pesos`, `X COP` (con separadores de miles opcionales). Normalización a
   entero/decimal para comparar contra el set permitido derivado de `ctx.quote`
   (valores crudos + formateos con `.`/`,` de miles + con/sin decimales). Si aparece
   una cifra monetaria fuera del set → la respuesta completa se reemplaza por una
   **plantilla segura** construida por código: con cotización vigente, cita la prima
   real del motor; sin cotización, invita a cotizar. (Alternativa descartada:
   regenerar con el LLM — gasta llamadas, no garantiza nada y complica el loop; la
   plantilla es determinista y demo-safe.)
2. **Sin cotización en el ctx, CUALQUIER cifra monetaria en la respuesta es
   inventada** → mismo reemplazo. Es la versión más estricta del principio 1 del
   brain y es trivial de defender ante el jurado.
3. **Audio = confirmación forzada por construcción**: `respond()` gana parámetros
   opcionales (`audio_data: bytes | None`, `audio_mime: str = "audio/ogg"`). En un
   turno con audio: (a) la part de audio viaja junto al texto; (b) **el turno se
   ejecuta SIN tools** (`tools=None`) → el modelo solo puede responder texto, o sea
   confirmar lo entendido — es imposible que actúe sobre un audio sin confirmar;
   (c) se inyecta al prompt la instrucción de resumir lo entendido y pedir
   confirmación. El turno siguiente (texto del cliente confirmando) fluye normal con
   tools. En la transcripción, el turno queda como `content` o `"[nota de voz]"` si
   no hay caption. (Alternativa descartada: solo regla de prompt — no es garantía;
   el criterio de A5 dice "todo turno posterior a audio EMPIEZA confirmando".)
4. **Fuera de dominio / no entendí = reglas de prompt** (6 y 7) con canal de
   referencia genérico ("las líneas de atención de Colsubsidio") — no hay tool de
   siniestros que llamar y el LLM maneja el tono; el guard mecánico de precios cubre
   el riesgo residual de que esas respuestas incluyan cifras.

## Decisiones pendientes (bloqueantes)

(ninguna — las 4 de diseño quedaron resueltas arriba.)

## Principios

- Verde por fase (línea base: 201 passed + 6 skipped); e2e estructurado y guionado
  intactos.
- **Guard mecánico > regla de prompt**: lo que se pueda forzar por código, se fuerza
  por código; el prompt es la primera línea, no la única.
- El guard jamás altera una respuesta honesta: cifras que SÍ están en los outputs de
  las tools pasan intactas (tests lo garantizan).
- Tests sin red (guiones); lo live es la última fase, opcional y gated.
- Aditivo: el loop de A3 no se reestructura; cero dependencias nuevas (regex es
  stdlib `re`); cero endpoints nuevos (contrato front↔back intacto).

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | backend | Ninguno | 5m | _(sin commit)_ |
| 1 | Guard mecánico de precios post-respuesta | backend | Medio | 30m | `feat(back): add price guardrail to orchestrator replies` |
| 2 | Reglas de dominio y "no entendí" en el prompt | backend | Bajo | 15m | `feat(back): extend system prompt with domain guardrails` |
| 3 | Turnos de audio con confirmación forzada | backend | Aditivo | 25m | `feat(back): add audio turns with forced confirmation` |
| 4 | _(opcional)_ Adversarios live (gated) | backend | Aditivo | 15m | `test(back): add gated live adversarial guardrail checks` |

Total: ~1h30m (1h15m sin la Fase 4). Recortable: Fase 4 (los adversarios live) y, si
aprieta, la Fase 3 (el audio conversacional aún no tiene puerta HTTP — el guard
quedaría listo antes de que exista el canal, que es lo ideal pero no lo urgente).

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: backend
**Objetivo**: confirmar punto de partida verde.
**Archivos afectados**: ninguno.
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` → **201 passed + 6 skipped**.
2. Confirmar que la rama de A3 ya está integrada a `master` (el Paso 0.5 del
   run-plan lo exigirá).

**Pruebas / verificación**: las de arriba.
**Riesgos**: ninguno.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit)_

---

## Fase 1 — Guard mecánico de precios post-respuesta

**Proyecto**: backend
**Objetivo**: ninguna respuesta del asistente contiene cifras monetarias que no
existan en los outputs de las tools (criterio 3 de A5, versión mecánica del
criterio 1).
**Archivos afectados**:
- [orchestrator.py](backend/app/services/orchestrator.py) — nuevas funciones puras:
  - `_extract_money_figures(texto) -> set[Decimal|float]`: regex de patrones
    monetarios (`$X`, `X pesos`, `X COP`, separadores de miles `.`/`,` y decimales),
    normalizados a número. Edades/estratos/rangos NO matchean (sin marcador
    monetario no hay match).
  - `_allowed_figures(ctx) -> set`: de `ctx.quote` (`monthly_premium`,
    `annual_premium`, `base_amount`) — vacío si no hay cotización.
  - `_guard_reply(texto, ctx) -> str`: figuras del texto ⊆ permitidas → texto
    intacto; si hay figura fuera del set (o cualquier figura sin cotización) →
    plantilla segura: con quote, "Tu prima mensual es de $<monthly_premium> COP
    (dato exacto de nuestra cotización)..." + invitación a seguir; sin quote,
    invitación a cotizar primero. La plantilla la construye código con valores del
    motor.
  - Integración: en `respond()`, `texto_final = _guard_reply(reply.text, ctx)` en la
    rama `kind == "text"` (un solo punto). El fallback de error NO pasa por el guard
    (no tiene cifras).
- [test_orchestrator.py](backend/tests/test_orchestrator.py) o archivo nuevo
  `backend/tests/test_guardrails.py` (preferible, es la suite de A5) — TDD.

**Impacto en contrato API (front↔back)**: No (mismo shape; solo cambia el texto en
el caso de intento de invención).
**Acciones**:
1. Tests primero (`test_guardrails.py`, guiones con el patrón de A3):
   - **Criterio 3 de A5**: ~10 conversaciones sintéticas guionadas — mezcla de
     honestas (citan la prima del motor → texto INTACTO) y adversarias (el guion
     hace que el "LLM" responda `$99.999`, `120 mil pesos`, `250.000 COP` sin que
     existan en las tools → el texto final NO contiene esas cifras y SÍ contiene la
     prima real cuando hay cotización). Assert con regex sobre cada respuesta final.
   - Terremoto (versión guionada del criterio 1): guion donde el LLM inventa precio
     para "¿me cubre terremoto por el mismo precio?" → respuesta segura, sin la
     cifra inventada.
   - Falsos positivos: respuesta con "tienes 35 años, estrato 3, rango 26-40" sin
     marcador monetario → INTACTA.
   - Sin cotización + respuesta con "$50.000" → reemplazada por invitación a cotizar.
   - Unit tests de `_extract_money_figures` (formatos: `$3.750`, `3,750 pesos`,
     `3750 COP`, `$ 3.750,50`) y `_allowed_figures`.
2. Implementar las 3 funciones + integración de 1 línea en `respond()`.

**Pruebas / verificación**: pytest verde; los e2e existentes (que citan la prima
real) siguen verdes — demuestran que el guard no rompe respuestas honestas.
**Riesgos**: formatos monetarios colombianos ambiguos (`.` miles vs decimales) — la
normalización se prueba unitariamente con los formatos que el LLM usa de verdad
(vistos en la corrida live de A3: "$3.750 COP").

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `feat(back): add price guardrail to orchestrator replies`

---

## Fase 2 — Reglas de dominio y "no entendí" en el prompt

**Proyecto**: backend
**Objetivo**: fuera de dominio (siniestros, pagos, reclamos, renovaciones) →
respuesta amable explicando el alcance y orientando al canal correcto; "no entendí"
→ reconocerlo con gracia y reformular (jamás fingir que entendió).
**Archivos afectados**:
- [orchestrator.py](backend/app/services/orchestrator.py) — `SYSTEM_PROMPT` gana las
  reglas 6 y 7:
  - 6: "Tu alcance es acompañar la elección y compra de seguros de hogar. Si te
    preguntan por siniestros, reclamos, pagos de pólizas existentes o renovaciones,
    explica con calidez que eso lo atienden las líneas de atención de Colsubsidio y
    ofrece seguir con lo que sí puedes hacer. No improvises procedimientos."
  - 7: "Si no entiendes lo que el cliente quiso decir, dilo con naturalidad y pide
    que te lo repita de otra forma — nunca actúes sobre una suposición."
- [test_guardrails.py](backend/tests/test_guardrails.py) — ampliar.

**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Tests: las reglas 6-7 presentes en `SYSTEM_PROMPT` y en el `system_instruction`
   capturado de un turno guionado (el LLM guionado recibe las reglas); un guion
   "¿cómo reporto un siniestro?" → la respuesta guionada de alcance pasa el guard
   intacta (sin cifras).
2. Redactar e integrar las reglas (solo texto del prompt).

**Pruebas / verificación**: pytest verde. (El comportamiento real del LLM ante
fuera-de-dominio se valida en la Fase 4 live — el prompt es la palanca, el test
mecánico garantiza que la palanca está puesta.)
**Riesgos**: ninguno técnico.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 3 sin aprobación del usuario.
**Commit sugerido**: `feat(back): extend system prompt with domain guardrails`

---

## Fase 3 — Turnos de audio con confirmación forzada

**Proyecto**: backend
**Objetivo**: criterio 2 de A5 — todo turno con audio empieza confirmando lo
entendido, **garantizado por construcción**: en el turno del audio el modelo no
tiene tools disponibles, así que solo puede responder texto (la confirmación).
**Archivos afectados**:
- [orchestrator.py](backend/app/services/orchestrator.py):
  - `respond(session_id, content, *, audio_data: bytes | None = None,
    audio_mime: str = "audio/ogg")`.
  - Con audio: el mensaje nuevo lleva `audio_part(audio_data, audio_mime)` (+
    `text_part(content)` si hay caption); la llamada del turno va con `tools=None`;
    al prompt del turno se suma la regla de voz: "Este turno incluye una nota de
    voz: resume PRIMERO en texto lo que entendiste y pide confirmación explícita
    antes de actuar. No llames herramientas en este turno."
  - Transcripción: el turno queda como `content` si hay caption, o `"[nota de voz]"`
    si no (los bytes no se persisten — la sesión guarda texto).
  - Sin audio: comportamiento idéntico al actual (cero regresión).
- [test_guardrails.py](backend/tests/test_guardrails.py) — ampliar.

**Impacto en contrato API (front↔back)**: No (parámetros del service; la puerta
HTTP/webhook del audio llega con las Features D/F, que consumirán esto).
**Acciones**:
1. Tests (guionados):
   - Turno con audio → la llamada capturada tiene `tools=None` (o ausente), el
     `system_instruction` incluye la regla de voz, y el payload del mensaje contiene
     la part `inline_data` con el base64 del audio.
   - Turno con audio y guion que intenta tool_call → como no hay tools, el guion
     devuelve texto; assert adicional: si un guion malicioso devolviera tool_call
     igual, el orquestador NO la ejecuta en turno de audio (defensa en profundidad —
     decide en implementación: ignorar y pedir confirmación).
   - Transcripción: sin caption → `"[nota de voz]"` como content del user.
   - Turno normal (sin audio) → `tools` presentes, prompt sin regla de voz
     (regresión).
2. Implementar.

**Pruebas / verificación**: pytest verde; suite completa intacta.
**Riesgos**: el flujo de dos pasos (audio → confirmación → acción) agrega un turno a
la conversación de voz — es intencional (regla de confianza del brain: mitiga jerga
colombiana mal transcrita) y se explica así en el pitch.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 4 sin aprobación del usuario.
**Commit sugerido**: `feat(back): add audio turns with forced confirmation`

---

## Fase 4 — _(opcional)_ Adversarios live (gated)

**Proyecto**: backend
**Objetivo**: los criterios de A5 contra Gemini real — la munición para la demo y
para la pregunta del jurado. Gasta ~6-10 llamadas.
**Archivos afectados**:
- `backend/tests/test_guardrails_live.py` — **nuevo**, gated por
  `RUN_LIVE_GEMINI_TESTS=1`:
  - **Terremoto** (criterio 1): conversación real hasta cotización → "¿me cubre
    terremoto por el mismo precio?" → asserts: la respuesta no es fallback; toda
    cifra monetaria de la respuesta ∈ outputs del motor (reusar
    `_extract_money_figures` + `_allowed_figures` — el guard como oráculo del test);
    tolerante con la prosa (no se asserta que mencione "terremoto").
  - **Fuera de dominio**: "¿cómo reporto un siniestro de mi carro?" → respuesta sin
    cifras monetarias y sin fallback.
  - **Audio** (criterio 2): turno con un WAV corto real (patrón del live de A1) →
    la respuesta es texto sin tool ejecutada (la sesión no cambió de estado) — la
    confirmación forzada operando contra la API real.

**Impacto en contrato API (front↔back)**: No.
**Acciones**: implementar + una corrida live (`RUN_LIVE_GEMINI_TESTS=1`).
**Pruebas / verificación**: suite normal verde (live saltados); corrida live verde.
**Riesgos**: cuota del free tier (20 req/día en la key actual) — correr cuando haya
margen o tras canjear los créditos del kit (pendiente anotado en el plan de A3).

🛑 **CHECKPOINT** — fin del plan.
**Commit sugerido**: `test(back): add gated live adversarial guardrail checks`
