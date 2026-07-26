# Plan — A6: Nombre del cliente en el saludo · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-26 · **Tipo**: plan de implementación por fases.
> **Base**: [20260725-a4-enriquecimiento-perfil-conversacion.plan.md](.claude/analysis/plans/20260725-a4-enriquecimiento-perfil-conversacion.plan.md)
> (✅ en master: whitelist de `EnrichmentService`, tool `enriquecer_perfil`, tabla
> `perfil_enriquecido` y memoria por SERIE — A6 es exactamente "un campo más"
> sobre esa infraestructura) y
> [20260725-a3-orquestador-conversacional-llm.plan.md](.claude/analysis/plans/20260725-a3-orquestador-conversacional-llm.plan.md)
> (el system prompt que ordena "saluda por su nombre si ya lo sabes" y el patrón
> `_scripted_llm` de sus tests).
> Tarea del vault: `07 - Tareas/Feature A - Agente conversacional/A6 - Nombre del cliente en el saludo.md`
> (sin dependencias; capa back; estimación 1h; pulido de demo — si el freeze
> aprieta, se suelta antes que C5/H8/H7/H5).
> **Proyectos afectados**: backend.
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

Cerrar la brecha detectada al completar A4: el system prompt ordena desde A3
"saludas con calidez (por su nombre si ya lo sabes)"
([orchestrator.py:55-56](backend/app/services/orchestrator.py#L55-L56)) pero esa
condición **nunca se cumple** — la base es anónima y `nombre` no está en la
whitelist de `EnrichmentService`. A6 captura el nombre como dato enriquecido
(persistente y con memoria por SERIE, gratis por A4), se lo entrega al agente al
perfilar, y el prompt le ordena pedirlo con naturalidad y usarlo en saludo y
cierre. Ganancia desproporcionada para el video: "Hola Carlos, cuéntame de tu
apartamento…".

Criterio de aceptación del vault:
1. El nombre se captura como dato enriquecido y el agente lo usa al saludar
   (test de conversación: el cliente se presenta → la siguiente respuesta lo
   nombra).

## Contexto / hallazgos del análisis

**Todo el andamiaje ya existe (A4 ✅ en master, verificado post-B5):**
- Whitelist con validadores por campo:
  [enrichment.py:50-58](backend/app/services/enrichment.py#L50-L58) — agregar
  `nombre` es una entrada + un validador (patrón de
  [_validate_ocupacion](backend/app/services/enrichment.py#L38-L44)).
- Tool `enriquecer_perfil` con enum de campos:
  [agent_tools.py:585-593](backend/app/services/agent_tools.py#L585-L593) —
  agregar `"nombre"` al enum y mencionarlo en la description.
- El mapeo a señales del motor
  ([_apply_enriched_field](backend/app/services/agent_tools.py#L153)) NO debe
  tocar `nombre`: **no es señal de riesgo, es personalización** (nota explícita
  de la tarea) — los campos sin mapeo (mascota/fumador/ocupacion) ya siguen ese
  camino: solo persisten.

**El hueco real para "saludar en la sesión siguiente":** dentro de una sesión el
LLM recuerda el nombre por el historial; pero en una sesión NUEVA de la misma
SERIE, el nombre está en la tabla y **nada se lo muestra al LLM** —
`_perfilar_cliente` consulta `fields_for(...)` para las señales pero su resultado
no incluye los campos sin mapeo. Solución mínima: el resultado de
`perfilar_cliente` gana una clave `datos_enriquecidos` (el dict `campo→valor` de
lo recordado) — el LLM la ve en el tool result y puede saludar por nombre (y de
paso mencionar mascota/ocupación con naturalidad). Aditivo, JSON-safe, sin tocar
`ProfileData` ni el contrato HTTP.

**El "test de conversación" del criterio es viable sin LLM real:** los tests del
orquestador ya guionan a Gemini con
[_scripted_llm](backend/tests/test_orchestrator.py#L27-L52) (function_calls +
texto, cero red). Un guion "el cliente se presenta → el LLM llama
`enriquecer_perfil(nombre)` → responde nombrándolo" prueba el plumbing completo
(tabla incluida) de forma determinista; el comportamiento del LLM real queda como
verificación manual (requiere `GEMINI_API_KEY`).

**B5 acaba de tocar los mismos archivos** (enum `categoria`, tool
`consultar_vehiculo`, campos de vehículo en `ProfileData`, prompt por categoría)
— sin colisión conceptual con A6, pero el conteo de declaraciones de tools
subió: si algún test fija el número exacto de tools (como pasó en A4 con
`test_has_six_unique_declarations_with_required_keys`,
[test_agent_tools.py](backend/tests/test_agent_tools.py)), A6 NO lo cambia
(no agrega tools, solo un valor al enum de una existente).

**Validador de `nombre` (pasos sugeridos de la tarea):** no vacío tras trim,
largo máximo 60, **sin dígitos**; conserva capitalización tal cual la declaró el
cliente (no title-case forzado — "María del Mar" ya viene bien).

## Decisiones pendientes (bloqueantes)

(ninguna — las tres micro-decisiones quedan fijadas: validador sin dígitos/≤60/
conserva capitalización; `nombre` NO entra al motor; la entrega al LLM en
sesiones nuevas va por `datos_enriquecidos` en el resultado de
`perfilar_cliente`, no por `ProfileData`.)

## Principios

- **Un campo más, cero arquitectura nueva**: A6 monta TODO sobre A4; si algo pide
  más que una entrada de whitelist + enum + prompt, es señal de sobre-diseño.
- El nombre jamás llega al motor de propensión ni a `ProfileData` — separación
  personalización vs. señal de riesgo, defendible ante el jurado.
- Aditivo puro: ningún test existente se edita; contrato HTTP intacto.
- Verde por fase (`.venv\Scripts\python.exe -m pytest -q` desde `backend/`),
  TDD-light, cero dependencias, cero env vars.

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | backend | Ninguno | 5m | _(sin commit)_ |
| 1 | Campo `nombre` en whitelist + tool + memoria al perfilar | backend | Aditivo | 25m | `feat(back): capture client name as enriched profile field` |
| 2 | Prompt de saludo + test de conversación guionada | backend | Bajo (prompt) | 20m | `feat(back): greet the client by name in conversation` |

Total: ~50m (la tarea estima 1h).

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: backend
**Objetivo**: punto de partida verde tras los merges de B5/A4.
**Archivos afectados**: ninguno.
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` → línea base
   (registrar conteo).
2. Confirmar (read-only) que `ALLOWED_FIELDS` sigue en
   [enrichment.py:50-58](backend/app/services/enrichment.py#L50-L58) sin campo
   `nombre`, y que el enum de la tool está en
   [agent_tools.py:585-593](backend/app/services/agent_tools.py#L585-L593).
3. `npm run build` opcional (frontend no se toca).

**Pruebas / verificación**: las de arriba.
**Riesgos**: ninguno.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit)_

---

## Fase 1 — Campo `nombre` en whitelist + tool + memoria al perfilar

**Proyecto**: backend
**Objetivo**: el nombre se captura, persiste (sesión y SERIE) y vuelve al agente
al perfilar en sesiones futuras — sin tocar el motor.
**Archivos afectados**:
- [enrichment.py](backend/app/services/enrichment.py) — `_validate_nombre(valor)`
  (strip; vacío → ValueError; `len > 60` → ValueError; `any(ch.isdigit())` →
  ValueError; devuelve el texto tal cual tras strip) + entrada `"nombre"` en
  `ALLOWED_FIELDS`.
- [agent_tools.py](backend/app/services/agent_tools.py) —
  - Enum de `_ENRIQUECER_PERFIL_DECLARATION` gana `"nombre"`; la description
    menciona el nombre ("…apenas el cliente se presente o mencione un dato…").
  - `_apply_enriched_field`: `nombre` explícitamente SIN mapeo (comentario de una
    línea: personalización, no señal — no toca `ProfileData`).
  - `_perfilar_cliente`: el dict `enriched` que ya consulta se expone en el
    resultado como `"datos_enriquecidos": enriched` (strings campo→valor; `{}`
    si no hay nada). Nada más cambia.
- Tests (ampliar `tests/test_enrichment.py` y `tests/test_agent_tools.py`, solo
  clases nuevas):
  - `record("sess","S1","nombre","Carlos")` → devuelve y persiste `"Carlos"`;
    `"  María del Mar "` → `"María del Mar"` (trim, capitalización intacta).
  - Inválidos → ValueError: vacío, `"C4rlos"` (dígitos), 61+ caracteres.
  - Tool: `enriquecer_perfil {campo: "nombre", valor: "Carlos"}` →
    `persistido: true` y **el perfil de señales no cambia** (mismo
    `recomendar_seguro` antes y después — el nombre no re-rankea).
  - Memoria: sesión A perfila SERIE + enriquece nombre; sesión B nueva perfila la
    misma SERIE → `result["datos_enriquecidos"]["nombre"] == "Carlos"`.
  - `datos_enriquecidos` presente como `{}` cuando no hay datos (shape estable,
    JSON-safe).

**Impacto en contrato API (front↔back)**: No — `datos_enriquecidos` viaja solo en
el resultado de la tool hacia el LLM; `ProfileData` y las rutas no cambian.
**Acciones**:
1. TDD-light: tests primero (rojo: `nombre` no está en la whitelist ni el enum;
   `datos_enriquecidos` no existe).
2. Implementar validador + enum + resultado de perfilar.
3. Suite completa verde.

**Pruebas / verificación**: pytest completo verde; ningún test existente editado.
**Riesgos**: mínimos — si B5 dejó algún test contando los CAMPOS del enum,
ajustarlo sería edición legítima prevista (reportarla en el checkpoint).

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `feat(back): capture client name as enriched profile field`

---

## Fase 2 — Prompt de saludo + test de conversación guionada

**Proyecto**: backend
**Objetivo**: el agente pide el nombre con naturalidad, lo registra y lo usa —
criterio del vault probado con LLM guionado.
**Archivos afectados**:
- [orchestrator.py](backend/app/services/orchestrator.py) — en el SYSTEM_PROMPT,
  junto a la línea de enriquecimiento (no como regla dura): al iniciar la
  conversación pregunta el nombre con naturalidad ("¿con quién tengo el gusto?")
  si aún no lo sabes; cuando el cliente se presente, regístralo con
  `enriquecer_perfil` (campo `nombre`) y úsalo en el saludo y el cierre; si
  `perfilar_cliente` devuelve `datos_enriquecidos` con `nombre`, salúdalo por él
  sin volver a preguntar.
- Tests (`tests/test_orchestrator.py` o archivo nuevo
  `tests/test_greeting_by_name.py`, con el patrón
  [_scripted_llm](backend/tests/test_orchestrator.py#L27-L52) + engine in-memory
  monkeypatcheado como en los tests de A4):
  - **Criterio del vault**: turno "Hola, soy Carlos" con guion: reply 1 =
    function_call `enriquecer_perfil {campo: "nombre", valor: "Carlos"}`;
    reply 2 = texto "¡Hola, Carlos! Cuéntame, ¿qué quieres proteger hoy?".
    Asserts: la tabla quedó con `nombre=Carlos` para la sesión
    (`EnrichmentService.fields_for`), el mensaje assistant final contiene
    "Carlos", y el `function_response` reportado al LLM llevó
    `persistido: true`.
  - El system_instruction enviado al LLM (capturado en `.calls`) contiene la
    instrucción del nombre ("con quién tengo el gusto" o equivalente — assert
    por substring estable).
- Verificación manual (fuera de CI, requiere `GEMINI_API_KEY` — se OMITE en
  `/launch-plan` y queda anotada): chat real "Hola, soy Carlos" → responde
  nombrándolo; sesión nueva con la misma SERIE → saluda "Hola Carlos" de
  entrada.

**Impacto en contrato API (front↔back)**: No — solo texto del prompt y tests; el
front recibe los mismos shapes (el nombre aparece dentro del texto libre del
assistant).
**Acciones**:
1. TDD-light: test guionado primero (rojo: el prompt no menciona el nombre y el
   guion aún funciona pero el assert del system_instruction falla).
2. Línea(s) del prompt.
3. Suite completa verde.

**Pruebas / verificación**: pytest completo verde. Manual opcional descrita
arriba.
**Riesgos**: prompt frágil ante reescrituras futuras (B5/H4 lo editan seguido) →
el assert usa un substring corto y estable, no el texto completo.

🛑 **CHECKPOINT** — fin del plan.
**Commit sugerido**: `feat(back): greet the client by name in conversation`

---

## Deuda / fuera de alcance (anotada para el vault)

- **Mostrar el nombre en la UI del chat** (header "Conversando con Carlos"):
  pulido de frontend, no lo pide la tarea.
- **Usar `datos_enriquecidos` completos en el saludo** (mascota/ocupación:
  "¿cómo está tu perro?") — el dato ya llega al LLM desde esta fase; afinar el
  prompt para explotarlo es guion de demo (H4), no código.
- **Privacidad**: el nombre queda en `perfil_enriquecido` como cualquier dato
  declarado; si el pitch lo pregunta, la respuesta es la misma de A4 (dato
  declarado con consentimiento conversacional, tabla borrable por sesión/serie).
