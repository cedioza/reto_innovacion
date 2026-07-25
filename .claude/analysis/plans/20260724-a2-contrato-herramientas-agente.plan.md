# Plan — A2: Contrato de herramientas del agente · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-24 · **Tipo**: plan de implementación por fases.
> **Base**: [20260724-a1-cliente-gemini-function-calling.plan.md](.claude/analysis/plans/20260724-a1-cliente-gemini-function-calling.plan.md)
> (ejecutado: `gemini_client.py` ya envía `tools` en formato function declarations y
> devuelve tool calls parseadas — este plan define QUÉ tools). Insumo externo: tarea
> **A2** del brain (`07 - Tareas/Feature A - Agente conversacional/A2 - Contrato de
> herramientas del agente.md`) y sus relaciones (`04 - Tecnología/Stack y
> arquitectura.md` — funnel con las 5 tools; `02 - Idea y Negocio/Matriz de
> Perfilamiento y Captura de Datos (IA + API).md` — args de perfilar por categoría),
> más la tarea A3 (consumidora del contrato).
> **Proyectos afectados**: backend.
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

Crear `backend/app/services/agent_tools.py`: las **5 herramientas del orquestador**
definidas y mapeadas a los services que YA existen, cada una con su **declaración
Gemini** (name/description/parameters JSON-schema) y su **handler Python** que devuelve
un resultado serializable para el LLM:

| Tool | Service existente | Qué devuelve al LLM |
|---|---|---|
| `perfilar_cliente` | [AffiliateService](backend/app/services/affiliate.py) | perfil resuelto (base anonimizada o declarado) + si es afiliado |
| `recomendar_seguro` | [PropensityService](backend/app/services/propensity.py) | producto + score + **razones estructuradas** del motor |
| `cotizar` | [QuoteService](backend/app/services/quote.py) | prima mensual/anual, coberturas, exclusiones |
| `ajustar_comparar` | [QuoteService](backend/app/services/quote.py) (adjustments) | cotización actual vs propuesta + ajustes disponibles |
| `cerrar_venta` | [ConsentService](backend/app/services/consent.py) | solicitud lista para pago con evidencia de consentimiento |

A2 es **el pegamento**: no toca la lógica de ningún motor. A2 bloquea A3 (orquestador);
es paralelizable con A1 (ya ejecutada).

## Contexto / hallazgos del análisis

**Del código (leído completo):**

- Las **razones ya vienen estructuradas** como exige el criterio de aceptación:
  [propensity.py:23-27](backend/app/services/propensity.py#L23-L27) produce
  `{code, label, evidence}` — el handler solo las pasa; no hay que tocar el motor.
- [AffiliateService.resolve()](backend/app/services/affiliate.py#L32-L52) ya implementa
  las dos vías de la Matriz de Perfilamiento (documento → base; declarado → prospecto)
  con fallback a perfil mínimo: `perfilar_cliente` mapea 1:1. Documento inexistente →
  cae a la vía declarada **sin error** (criterio de aceptación cubierto por diseño).
- [QuoteService.calculate_quote()](backend/app/services/quote.py#L18-L63) ya acepta
  `selected_adjustments: list[str]` y devuelve un dict JSON-safe con
  `adjustment_details` — sirve tanto para `cotizar` como para `ajustar_comparar`.
  Los ajustes disponibles salen de `product.adjustments` vía `CatalogService`.
- [ConsentService.capture()](backend/app/services/consent.py#L27-L65) necesita
  `session_id, product_id, profile, recommendation, quote` y produce
  `ConsentedApplication` (Pydantic → `.model_dump()` es serializable directo).
- [gemini_client.py](backend/app/services/integrations/gemini_client.py) (A1) espera
  `tools` como lista de declarations `{name, description, parameters}` y devuelve
  `GeminiReply(kind="tool_call", tool_name, tool_args)` — el registro de A2 exporta
  exactamente ese formato.
- Capas: `agent_tools.py` va en `app/services/` y **solo compone services** (patrón
  orquestador permitido por [backend/CLAUDE.md](backend/CLAUDE.md)); jamás importa
  repositorios ni ejecuta queries.

**Decisión de diseño central — el contexto de sesión NO viaja por el LLM:**

`cerrar_venta` (y en parte `cotizar`/`recomendar_seguro`) necesitan el estado del
funnel (perfil resuelto, recomendación, cotización). Si esos datos llegaran como args
de la tool call, el LLM podría re-escribirlos — **un precio alterado por el LLM en un
producto financiero es descalificatorio** (regla de oro del brain: "los datos de
productos/precios nunca salen de la generación libre del LLM"). Por eso el contrato es:

```python
@dataclass
class ToolContext:
    """Estado del funnel que las tools leen/escriben — LO POSEE EL CÓDIGO, no el LLM."""
    session_id: str = ""
    profile: ProfileData | None = None        # lo setea perfilar_cliente
    recommendation: dict | None = None        # lo setea recomendar_seguro
    quote: dict | None = None                 # lo setea cotizar / ajustar_comparar

# Registro
@dataclass
class AgentTool:
    declaration: dict                          # formato Gemini (name/description/parameters)
    handler: Callable[[dict, ToolContext], dict]

AGENT_TOOLS: dict[str, AgentTool]
def tool_declarations() -> list[dict]: ...    # se pasa directo a generate_reply(tools=...)
def execute_tool(name: str, args: dict, ctx: ToolContext) -> dict: ...
```

- Los **args** de cada declaración llevan solo lo que el cliente dice en la
  conversación (documento, datos declarados del hogar, códigos de ajustes,
  consentimiento). El estado calculado vive en `ToolContext`, que A3 persistirá en la
  sesión.
- `execute_tool` con nombre desconocido o contexto insuficiente (p. ej. `cerrar_venta`
  sin cotización previa) devuelve un **dict de error controlado**
  (`{"error": "...", "detail": "..."}`) — nunca excepción: el LLM puede alucinar
  nombres o saltarse pasos, y la respuesta de error le permite corregir el rumbo.
- Alternativa descartada: tools 100% stateless con todo por args — más simple, pero
  permite al LLM inyectar precios/perfiles; incompatible con la regla del reto.

**Alcance de los parámetros de `perfilar_cliente`**: la Matriz de Perfilamiento define
args por las 5 categorías; el motor actual solo evalúa **Hogar**. La declaración de A2
expone documento + los campos de Hogar que `ProfileData` ya soporta (`property_type`,
`zone`, `stratum`, `age_range`, `has_family`) — cuando B3/B4 traigan multi-categoría,
se amplían `parameters` **sin cambiar el contrato** (nota explícita de la tarea A2).

## Decisiones pendientes (bloqueantes)

(ninguna — la decisión de diseño del `ToolContext` quedó resuelta y documentada
arriba; los nombres de las tools son los del funnel del brain, en español.)

## Principios

- Verde por fase (línea base actual: **144 passed + 3 skipped**).
- **A2 es pegamento**: prohibido tocar la lógica de `propensity`/`quote`/`affiliate`/
  `consent`/`catalog`. Si un motor necesitara un cambio, se anota como hallazgo y se
  decide en el checkpoint — no se hace de contrabando.
- Los resultados de las tools devuelven las **razones del motor** tal cual (el LLM las
  explica, no las inventa).
- Tests unitarios **con los services reales** (son deterministas — no hay red);
  criterio de A2: "llamada con args válidos → resultado del servicio real serializado".
- Serializable = JSON-safe (dicts/lists/str/num/bool; Pydantic vía `.model_dump()`).
- Cero dependencias nuevas, cero env vars nuevas, cero endpoints (el HTTP llega en A3).
- Contrato front↔back: **ninguna fase lo toca**.

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | backend | Ninguno | 5m | _(sin commit)_ |
| 1 | Registro + `ToolContext` + `perfilar_cliente` | backend | Aditivo | 30m | `feat(back): add agent tools registry with perfilar cliente` |
| 2 | `recomendar_seguro` + `cotizar` | backend | Aditivo | 25m | `feat(back): add recommend and quote agent tools` |
| 3 | `ajustar_comparar` + `cerrar_venta` | backend | Aditivo | 25m | `feat(back): add adjust and close sale agent tools` |
| 4 | _(opcional)_ Smoke live: Gemini elige las tools reales | backend | Aditivo | 15m | `test(back): add gated live check for agent tool selection` |

Total: ~1h40m (1h25m sin la Fase 4, que es recortable — mismo patrón gated de A1).

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: backend
**Objetivo**: confirmar punto de partida verde.
**Archivos afectados**: ninguno.
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` → **144 passed + 3 skipped**.
2. Confirmar que no existe `backend/app/services/agent_tools.py` ni tests homónimos.

**Pruebas / verificación**: las de arriba.
**Riesgos**: ninguno.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit)_

---

## Fase 1 — Registro + `ToolContext` + `perfilar_cliente`

**Proyecto**: backend
**Objetivo**: el andamiaje del contrato (dataclasses, registro, `tool_declarations()`,
`execute_tool()` con error controlado) y la primera tool completa.
**Archivos afectados**:
- `backend/app/services/agent_tools.py` — **nuevo**: `ToolContext`, `AgentTool`,
  `AGENT_TOOLS`, `tool_declarations()`, `execute_tool(name, args, ctx)`; tool
  `perfilar_cliente`:
  - `parameters`: `document_number` (string, opcional) + declarados de Hogar
    (`property_type` house/apartment/other, `zone` urban/rural, `stratum` 1-6 int,
    `age_range` enum de la base, `has_family` bool) — todos opcionales (la Matriz:
    afiliado solo da documento; prospecto da declarados).
  - handler: construye `ProfileData` con los declarados → `AffiliateService.resolve()`
    → guarda el perfil resuelto en `ctx.profile` → devuelve
    `{"afiliado": bool, "fuente": "base"|"declarado", "profile": {...}}`.
- `backend/tests/test_agent_tools.py` — **nuevo**.

**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Implementar andamiaje + declaración + handler (arriba).
2. Tests (services reales, patrón determinista):
   - `tool_declarations()` → 1 entrada (crece por fase), cada una con
     `name`/`description`/`parameters` y names únicos.
   - `perfilar_cliente` con `document_number` existente en el CSV de prueba (usar el
     patrón de CSV temporal de [test_affiliates.py](backend/tests/test_affiliates.py)
     con `monkeypatch` de `settings.affiliate_csv_path`) → `afiliado: True`, perfil de
     la base, `ctx.profile` seteado.
   - **documento inexistente + declarados → vía "no afiliado" sin error** (criterio A2).
   - sin documento ni declarados → perfil mínimo por defecto (nunca excepción).
   - `execute_tool("tool_inexistente", ...)` → dict de error controlado, sin excepción.
   - el resultado es JSON-safe: `json.dumps(resultado)` no lanza.

**Pruebas / verificación**: `.venv\Scripts\python.exe -m pytest -q` verde.
**Riesgos**: ninguno (módulo nuevo aislado).

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `feat(back): add agent tools registry with perfilar cliente`

---

## Fase 2 — `recomendar_seguro` + `cotizar`

**Proyecto**: backend
**Objetivo**: las dos tools del corazón explicable del funnel.
**Archivos afectados**:
- [agent_tools.py](backend/app/services/agent_tools.py) — agregar:
  - `recomendar_seguro`: `parameters` vacíos u overrides opcionales del perfil; handler
    usa `ctx.profile` (si falta → error controlado "perfila primero") →
    `PropensityService.evaluate()` → guarda en `ctx.recommendation` → devuelve
    `{product_id, score, recommended, reasons: [{code, label, evidence}]}` tal cual
    del motor.
  - `cotizar`: `parameters`: `adjustments` (array de strings, opcional); handler usa
    `ctx.profile` (si falta → error controlado) → `QuoteService.calculate_quote()` →
    guarda en `ctx.quote` → devuelve el dict del motor + `product_id`.
- [test_agent_tools.py](backend/tests/test_agent_tools.py) — ampliar.

**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Implementar ambas tools (arriba).
2. Tests:
   - `recomendar_seguro` con perfil favorable (26-40, estrato 3, casa, urbano) →
     `recommended: True` y **`reasons` estructuradas `{code, label, evidence}`**
     (criterio A2) idénticas a llamar `PropensityService.evaluate()` directo.
   - `recomendar_seguro` sin `ctx.profile` → error controlado.
   - `cotizar` sin ajustes → prima idéntica a `QuoteService.calculate_quote()` directo
     (el LLM no puede alterar precios: mismo número, centavo a centavo).
   - `cotizar` con un ajuste válido del catálogo → `adjustment_details` refleja el
     ajuste; `ctx.quote` queda seteado.
   - resultados JSON-safe.

**Pruebas / verificación**: pytest verde.
**Riesgos**: ninguno.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 3 sin aprobación del usuario.
**Commit sugerido**: `feat(back): add recommend and quote agent tools`

---

## Fase 3 — `ajustar_comparar` + `cerrar_venta`

**Proyecto**: backend
**Objetivo**: cerrar el funnel: el frente 3 del reto (ajustar/comparar) y la
vinculación lista para pago.
**Archivos afectados**:
- [agent_tools.py](backend/app/services/agent_tools.py) — agregar:
  - `ajustar_comparar`: `parameters`: `adjustments` (array de strings) — la propuesta a
    comparar; handler: requiere `ctx.profile` y `ctx.quote` (error controlado si
    faltan) → recalcula con `QuoteService` → devuelve
    `{actual: {...}, propuesta: {...}, diferencia_mensual, ajustes_disponibles:
    [{code, name, description}]}` (los disponibles salen de
    `CatalogService.get_product("hogar-estandar").adjustments` — vía service, nunca
    repo) → actualiza `ctx.quote` a la propuesta.
  - `cerrar_venta`: `parameters`: `consentimiento` (boolean, requerido); handler:
    `consentimiento != true` → error controlado (el consentimiento explícito es regla
    de negocio); requiere `ctx.session_id`, `ctx.profile`, `ctx.recommendation`,
    `ctx.quote` completos (error controlado si falta algo — "el LLM se saltó pasos")
    → construye `Recommendation`/`QuoteDetail` desde el ctx →
    `ConsentService.capture()` → devuelve `ConsentedApplication.model_dump()`.
- [test_agent_tools.py](backend/tests/test_agent_tools.py) — ampliar.

**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Implementar ambas tools (arriba).
2. Tests:
   - `ajustar_comparar`: la diferencia mensual = propuesta − actual, calculada por el
     motor; `ajustes_disponibles` refleja el catálogo.
   - `cerrar_venta` con funnel completo → solicitud con `state: ready_for_payment`,
     `consent_timestamp` y los mismos valores de `ctx.quote` (precio intacto).
   - `cerrar_venta` sin consentimiento → error controlado; sin cotización previa →
     error controlado que menciona el paso faltante.
   - flujo integrado: perfilar → recomendar → cotizar → ajustar → cerrar con el mismo
     `ToolContext` (mini-e2e del contrato, sin LLM).

**Pruebas / verificación**: pytest verde.
**Riesgos**: `cerrar_venta` reconstruye Pydantic desde dicts del ctx — si A3 decide
persistir el ctx con otros tipos, se ajusta allá (el contrato de A2 no cambia).

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 4 sin aprobación del usuario.
**Commit sugerido**: `feat(back): add adjust and close sale agent tools`

---

## Fase 4 — _(opcional)_ Smoke live: Gemini elige las tools reales

**Proyecto**: backend
**Objetivo**: validar con la API real que las 5 declaraciones son aceptadas por Gemini
y que ante un mensaje típico el modelo **elige la tool correcta** — el eslabón
A1+A2 que A3 dará por sentado. Mismo patrón gated de A1 (gasta ~2 llamadas).
**Archivos afectados**:
- `backend/tests/test_agent_tools_live.py` — **nuevo**, gated por
  `RUN_LIVE_GEMINI_TESTS=1` (mismo `skipif` de
  [test_gemini_client_live.py](backend/tests/test_gemini_client_live.py)):
  - `generate_reply` con `tools=tool_declarations()` y mensaje "hola, quiero un
    seguro para mi casa, mi cédula es 12345" → Gemini responde (texto o tool_call);
    si es tool_call, el nombre existe en `AGENT_TOOLS` (las declaraciones son válidas
    — la API no rechaza el schema).
  - mensaje que fuerza cotización con perfil ya dado → `kind == "tool_call"` y
    `tool_name` ∈ {`cotizar`, `perfilar_cliente`} (tolerante: el LLM decide el orden,
    lo que se valida es que use el contrato).

**Impacto en contrato API (front↔back)**: No.
**Acciones**: las de arriba; correr una vez con
`RUN_LIVE_GEMINI_TESTS=1 .venv/Scripts/python.exe -m pytest tests/test_agent_tools_live.py -q`.
**Pruebas / verificación**: suite normal verde (live saltados); corrida live verde.
**Riesgos**: variación del LLM → asserts tolerantes (pertenencia al registro, no
igualdad exacta); si el schema de alguna declaración es rechazado por la API (400),
aquí se descubre y se corrige — mejor ahora que en A3.

🛑 **CHECKPOINT** — fin del plan.
**Commit sugerido**: `test(back): add gated live check for agent tool selection`
