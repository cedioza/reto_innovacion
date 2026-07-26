# Plan — B3: Propensión multi-categoría explicable · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-25 · **Tipo**: plan de implementación por fases.
> **Base**: [20260725-b1-catalogo-multiproducto-json.plan.md](.claude/analysis/plans/20260725-b1-catalogo-multiproducto-json.plan.md)
> (catálogo JSON con `category` por producto) y
> [20260725-b2-catalogo-4-categorias-restantes.plan.md](.claude/analysis/plans/20260725-b2-catalogo-4-categorias-restantes.plan.md)
> (5 categorías cargadas — `hogar`, `accidentes`, `vida`, `movilidad`, `credito` — y
> `calculate_quote(..., product_id=...)` ya acepta cualquier producto; su deuda
> anotada dice "B3/B5: la recomendación sigue siendo hogar hasta entonces").
> Tarea del vault: `07 - Tareas/Feature B - Catalogo y motores/B3 - Propension multicategoria explicable.md`
> (depende de **B1 ✅**; capa back; estimación 4h).
> **Proyectos afectados**: backend.
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

`PropensityService` puntúa **las 5 categorías del catálogo** para un perfil (base +
declarado) y devuelve un **ranking explicable** — cada categoría con score y razones
`code/label/evidence`. La recomendación **cambia según el perfil** (requisito no
negociable del reto): joven soltero → Accidentes; hijos/dependientes → Vida; vehículo
declarado → Movilidad; crédito declarado → Crédito; vivienda → Hogar. El scoring
completo queda en el log estructurado (evidencia de "lógica documentada, no caja
negra") y el funnel (recomendar → cotizar → cerrar) queda coherente con el producto
recomendado.

Criterios de aceptación del vault:
1. 5 perfiles de prueba (uno por categoría) → 5 recomendaciones distintas, cada una
   con ≥2 razones.
2. El mismo perfil siempre produce el mismo ranking (determinismo).
3. Un dato enriquecido cambia el ranking y aparece en las razones.

## Contexto / hallazgos del análisis

**El motor hoy es mono-categoría por diseño de la fase MVP:**
[propensity.py](backend/app/services/propensity.py) puntúa solo reglas de Hogar y
devuelve `product_id: "hogar-estandar"` fijo
([propensity.py:99](backend/app/services/propensity.py#L99)). Shape actual del
resultado: `{score, product_id, reasons[{code,label,evidence}], recommended}`.

**Callers de `evaluate()` (los 3 rastreados):**
- [agent_tools.py:191](backend/app/services/agent_tools.py#L191) — tool
  `recomendar_seguro`: guarda el dict en `ctx.recommendation` y lo devuelve al LLM.
- [conversation.py:96](backend/app/services/conversation.py#L96) — flujo REST
  (`POST /conversations/{id}/profile`): usa `product_id` y `reasons`, pero
  **hardcodea** `product_name="Hogar Estándar"`
  ([conversation.py:99](backend/app/services/conversation.py#L99)) y el texto del
  mensaje ([conversation.py:122](backend/app/services/conversation.py#L122)).
- [test_agent_tools.py:221](backend/tests/test_agent_tools.py#L221) — compara la
  tool contra el motor (auto-consistente: sigue verde con el motor nuevo).

**El orquestador LLM ya es multicategoría-ready:** resuelve `product_name` desde el
catálogo por el `product_id` que venga en `ctx.recommendation`
([orchestrator.py:176-183](backend/app/services/orchestrator.py#L176-L183),
[orchestrator.py:459-460](backend/app/services/orchestrator.py#L459-L460)) — si el
motor devuelve `vida-basico`, el chat y las tarjetas ya mostrarían "Vida Básico" sin
tocar nada. Los hardcodes que SÍ desalinean el funnel están en
[agent_tools.py:226](backend/app/services/agent_tools.py#L226) (`_cotizar` siempre
cotiza hogar), [agent_tools.py:285](backend/app/services/agent_tools.py#L285)
(`_ajustar_comparar` lista ajustes de hogar) y el flujo REST de arriba. `cerrar_venta`
ya lee `ctx.recommendation["product_id"]`
([agent_tools.py:362](backend/app/services/agent_tools.py#L362)) — coherente gratis.

**B2 dejó el cotizador listo:** `calculate_quote(profile, adjustments, product_id)`
([quote.py:18-23](backend/app/services/quote.py#L18-L23)) cotiza cualquier producto;
solo falta pasarle el recomendado. Los factores por categoría del JSON siguen
documentales — eso es **B4**, no B3.

**El perfil actual no tiene las señales que B3 exige:**
[ProfileData](backend/app/schemas/conversation.py#L23-L28) solo trae
`property_type/zone/stratum/age_range/has_family`. No hay campo de **vehículo**,
**crédito** ni **hijos** — sin ellos no existen las reglas "vehículo → Movilidad" ni
"crédito → Crédito". Hay que agregarlos como opcionales (aditivo) y exponerlos en la
tool [perfilar_cliente](backend/app/services/agent_tools.py#L70-L111) para que el LLM
los capture (la [Matriz del vault](C:/machine/development/progress/colsubsidio/colsubsidio-brain) los define como "Preguntado por la IA").
La persistencia en Postgres del perfil enriquecido es **A4** (pendiente, depende de
C3) — B3 solo necesita que el dato declarado **viaje al motor en la misma sesión**.

**Señales reales de la base (para calibrar evidencias):**
[AffiliateProfile](backend/app/models/affiliate.py) trae `household_segment`
(LAMBDA/RHO/…) y `population_segment`. El análisis del vault (`Análisis base de
afiliados`) aporta conteos citables: "21,7% del segmento RHO usa droguería vs 16,8%
de LAMBDA" y "50% de la base tiene 20-35 años" — se usan como `evidence` textual en
las reglas de Vida/familia cuando el perfil venga de la base. La calibración es
deseable, no bloqueante (nota del vault).

**Log estructurado:** hoy solo [consent.py:25](backend/app/services/consent.py#L25)
usa `logging`. B3 agrega un logger en el motor que registre el scoring completo
(todas las categorías, no solo la ganadora) en JSON — cero dependencias nuevas.

**Tests existentes que fijan el comportamiento viejo (edición deliberada, no
debilitamiento):**
- [test_propensity.py:37](backend/tests/test_propensity.py#L37) y
  [:73](backend/tests/test_propensity.py#L73) asertan `product_id == "hogar-estandar"`
  — el perfil de esos tests es de hogar y el perfil vacío cae al fallback hogar, así
  que **siguen válidos**; solo `test_young_age_reduces_score`
  ([:59](backend/tests/test_propensity.py#L59)) cambia de semántica (el score
  top-level pasa a ser el del ganador) → se reescribe comparando el score de la
  categoría `hogar` dentro del ranking.
- [test_e2e_happy_path.py:53](backend/tests/test_e2e_happy_path.py#L53) — perfil
  casa/urbano/26-40 sin más señales → con la tabla de pesos de abajo sigue ganando
  hogar. **No se toca.**

## Decisiones pendientes (bloqueantes)

(ninguna — las 5 categorías, ids de producto y señales salen del catálogo de B2 y de
la Matriz del vault; la tabla de pesos de abajo queda definida en este plan y los
tests fijan ganadores por perfil, no scores exactos, para permitir calibración fina
sin romper la suite.)

## Principios

- **Reglas como datos, no `if` gigante**: una tabla `CATEGORY_RULES` declarativa
  (categoría, condición sobre campos del perfil, peso, razón `code/label/evidence`).
  Agregar una regla = agregar una entrada.
- **Determinismo absoluto**: mismo perfil → mismo ranking; desempate por orden del
  catálogo (hogar primero). Nada de aleatoriedad ni de LLM en el motor.
- **Compatibilidad aditiva**: `evaluate()` conserva `score/product_id/reasons/
  recommended` (ahora: los del ganador) y **agrega** `ranking` — ningún caller se
  rompe; el LLM gana contexto para explicar alternativas.
- **El producto por categoría sale del catálogo** (primer producto con esa
  `category`), nunca de un mapa hardcodeado — se respeta la promesa de B1.
- Verde por fase (`.venv\Scripts\python.exe -m pytest -q` desde `backend/`), aditivo
  antes que destructivo, cero dependencias nuevas, cero env vars nuevas.
- Backend puro: el frontend no requiere cambios (shape del contrato intacto; los
  valores ya son dinámicos en las tarjetas D3).

## Tabla de señales (referencia de implementación de la Fase 2)

| Categoría | Señal (condición sobre el perfil) | Peso | Razón (`code`) |
|---|---|---|---|
| hogar | `property_type` ∈ (house, apartment) | +0.45 | `homeowner` |
| hogar | estrato 2-4 **y** hay `property_type` | +0.15 | `income_tier` |
| hogar | zona urbana **y** hay `property_type` | +0.10 | `zone_risk` |
| hogar | edad 18-25 | −0.10 | `age_risk` |
| vida | `has_children` True | +0.50 | `dependents` |
| vida | `has_family` True | +0.15 | `family_profile` |
| vida | edad 26-40 / 41-55 | +0.15 | `life_stage` |
| vida | `household_segment` ∈ (RHO, LAMBDA) (perfil base) | +0.10 | `family_segment` — evidence cita el conteo real ("21,7% del segmento RHO usa droguería") |
| accidentes | edad 18-25 | +0.40 | `young_profile` — evidence cita "50% de la base tiene 20-35 años" |
| accidentes | sin dependientes (`has_children` y `has_family` no True) | +0.15 | `no_dependents` |
| accidentes | zona urbana | +0.10 | `urban_exposure` |
| movilidad | `has_vehicle` True | +0.75 | `vehicle_declared` |
| movilidad | edad 18-25 **y** `has_vehicle` | +0.05 | `young_driver` |
| credito | `has_credit` True | +0.70 | `credit_declared` |
| credito | edad 26-40 / 41-55 **y** `has_credit` | +0.10 | `working_age` |

Scores clamp [0,1]; `recommended = score_ganador >= 0.5`; perfil sin señales → todas
en 0 → fallback determinista al primer producto del catálogo (hogar) con
`recommended: false`. Los pesos son punto de partida calibrable: los tests asertan
**qué categoría gana por perfil** (criterios del vault), no cifras exactas —
excepto el determinismo, que sí compara resultados completos.

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | backend | Ninguno | 5m | _(sin commit)_ |
| 1 | Señales declaradas en el perfil (`has_children/has_vehicle/has_credit`) | backend | Aditivo | 25m | `feat(back): capture vehicle, credit and children in profile` |
| 2 | Motor multi-categoría: reglas como datos + ranking + log estructurado | backend | Medio (motor) | 45m | `feat(back): rank all insurance categories with explainable reasons` |
| 3 | Funnel coherente: cotizar/ajustar/REST usan el producto recomendado | backend | Medio (funnel) | 30m | `feat(back): quote and close on the recommended product` |

Total: ~105m (dentro de las 4h de la tarea). B4 (factores por categoría + compare) y
B5 (preguntas por categoría) construyen encima; A4 agrega la persistencia BD del
perfil enriquecido.

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: backend
**Objetivo**: punto de partida verde y línea base registrada.
**Archivos afectados**: ninguno.
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` → registrar línea base
   (todo verde esperado tras el merge de B2).
2. Verificar que el catálogo trae las 5 categorías (rápido:
   `pytest -q tests/test_catalog_multiproduct.py`).
3. Frontend NO se toca; opcional `npm run build` desde `frontend/` solo como registro.

**Pruebas / verificación**: las de arriba.
**Riesgos**: ninguno.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit)_

---

## Fase 1 — Señales declaradas en el perfil

**Proyecto**: backend
**Objetivo**: el perfil puede transportar las señales que disparan Movilidad, Crédito
y Vida — declaradas en conversación (Fricción Cero de la Matriz: se preguntan solo si
hacen falta).
**Archivos afectados**:
- [conversation.py (schemas)](backend/app/schemas/conversation.py#L23-L28) —
  `ProfileData` gana 3 opcionales: `has_children: Optional[bool]`,
  `has_vehicle: Optional[bool]`, `has_credit: Optional[bool]` (default `None`).
- [agent_tools.py](backend/app/services/agent_tools.py#L70-L158) — la declaración de
  `perfilar_cliente` gana las 3 propiedades (con descripciones que digan cuándo
  preguntarlas) y `_perfilar_cliente` las copia de `args` al `ProfileData` resuelto
  (incluirlas en el chequeo `has_declared_data`). Ajustar la descripción de la tool
  para que no hable solo de "datos del hogar".
- Tests (`tests/test_agent_tools.py`, ampliar): `perfilar_cliente` con
  `has_vehicle=true` deja `ctx.profile.has_vehicle is True` y lo devuelve en
  `profile`; los 3 campos ausentes → `None` (no rompen el flujo actual); resultado
  sigue JSON-safe.

**Impacto en contrato API (front↔back)**: Sí — **aditivo e inocuo**: `ProfileData`
viaja dentro de `ConversationResponse.profile`, así que la respuesta gana 3 claves
opcionales (`null` por defecto). El frontend no lee esos campos (las tarjetas D3 usan
`recommendation`/`quote`) → **no requiere cambios en ningún otro lado**; se anota
aquí por transparencia del shape.
**Acciones**:
1. TDD-light: tests de la tool primero (rojos: la declaración no tiene los campos).
2. Ampliar `ProfileData` + declaración + handler.
3. Suite completa verde.

**Pruebas / verificación**: pytest completo verde; ningún test existente editado.
**Riesgos**: olvidar los campos nuevos en `has_declared_data` haría que un perfil
"solo vehículo" se descarte como vacío → cubierto por test explícito.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `feat(back): capture vehicle, credit and children in profile`

---

## Fase 2 — Motor multi-categoría: reglas como datos + ranking + log estructurado

**Proyecto**: backend
**Objetivo**: el corazón de B3 — `evaluate()` puntúa las 5 categorías con la tabla de
señales, devuelve el ranking completo con razones explicables y registra el scoring
en el log. Los 3 criterios de aceptación del vault quedan cubiertos por tests aquí.
**Archivos afectados**:
- [propensity.py](backend/app/services/propensity.py) — reescritura del motor:
  - `CATEGORY_RULES`: lista declarativa de reglas (categoría, `condition(profile)`,
    peso, builder de razón `code/label/evidence`) según la tabla de señales de este
    plan. Las reglas de hogar existentes se conservan (mismos `code` actuales) con el
    gate "estrato/zona solo si hay propiedad".
  - `evaluate(profile)` → dict **compatible + ampliado**:
    `{score, product_id, reasons, recommended}` = los del **ganador**, más
    `ranking: [{category, product_id, score, reasons}, ...]` ordenado desc, desempate
    por orden del catálogo. `product_id` de cada categoría = primer producto del
    catálogo con esa `category` (vía `CatalogService` — service compone service,
    permitido por [backend/CLAUDE.md](backend/CLAUDE.md)); si una categoría no tiene
    producto en el catálogo, se omite del ranking (robustez, no crash).
  - Logger `logging.getLogger(__name__)`: un `logger.info` por evaluación con JSON
    (`json.dumps`) del scoring completo — perfil resumido, score por categoría,
    códigos de razones y ganador. Evidencia de "lógica documentada".
- Tests (`tests/test_propensity_multicategory.py`, nuevo):
  - **Criterio 1**: 5 perfiles canónicos → 5 `product_id` distintos, cada uno con
    ≥2 razones `code/label/evidence`:
    hogar = casa/urbano/estrato 3/26-40 · vida = 26-40 + `has_children` +
    `has_family` · accidentes = 18-25/urbano sin dependientes · movilidad = 26-40 +
    `has_vehicle` · crédito = 41-55 + `has_credit`.
  - **Criterio 2 (determinismo)**: dos llamadas con el mismo perfil → `ranking`
    idéntico (comparación completa, scores incluidos).
  - **Criterio 3 (dato enriquecido)**: perfil hogar completo gana hogar; el MISMO
    perfil + `has_vehicle=True` → gana `movilidad-auto` y alguna razón del ganador
    cita el vehículo (`vehicle_declared`).
  - Shape: `ranking` cubre las 5 categorías, scores en [0,1], resultado JSON-safe.
  - Perfil vacío → fallback hogar con `recommended is False`.
  - El log se emite (fixture `caplog`: el registro contiene los scores de las 5
    categorías).
- [test_propensity.py](backend/tests/test_propensity.py) — **única edición a tests
  existentes** (deliberada, sin debilitar): `test_young_age_reduces_score` pasa a
  comparar el score de la categoría `hogar` dentro de `ranking` (la aserción vieja
  comparaba el score top-level, que ahora es el del ganador y puede ser otra
  categoría). El resto del archivo queda intacto y debe seguir verde.

**Impacto en contrato API (front↔back)**: No — el shape de
`ConversationResponse.recommendation` (schema `Recommendation`) no cambia; `ranking`
viaja solo en el resultado de la tool hacia el LLM (más contexto para explicar) y en
`ctx.recommendation` interno. Ninguna ruta/status/env var cambia.
**Acciones**:
1. TDD-light: tests nuevos primero (rojos: hoy todo devuelve hogar).
2. Implementar `CATEGORY_RULES` + ranking + fallback + logger.
3. Ajustar la aserción de `test_young_age_reduces_score` (justificación en el
   docstring del test).
4. Suite completa verde — en particular
   [test_e2e_happy_path.py](backend/tests/test_e2e_happy_path.py) y
   [test_agent_tools.py](backend/tests/test_agent_tools.py) SIN editar.

**Pruebas / verificación**: pytest completo verde. Manual opcional:
`python -c` invocando `PropensityService().evaluate(...)` con 2 perfiles y ver el log
JSON en consola.
**Riesgos**: calibración de pesos que rompa el e2e (perfil casa debe seguir ganando
hogar) → la tabla de este plan ya lo garantiza (hogar 0.70 vs vida 0.15 en ese
perfil) y el e2e intacto lo vigila. Ranking sensible al orden del catálogo → el
desempate documentado lo hace explícito y testeado.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 3 sin aprobación del usuario.
**Commit sugerido**: `feat(back): rank all insurance categories with explainable reasons`

---

## Fase 3 — Funnel coherente: cotizar/ajustar/REST usan el producto recomendado

**Proyecto**: backend
**Objetivo**: que recomendar Vida y cotizar Hogar sea imposible — el funnel completo
(tools del LLM y flujo REST) opera sobre el producto que recomendó el motor. Sin esto,
B3 haría el demo **incoherente**. (B2 ya dejó `calculate_quote` paramétrico; aquí solo
se le pasa el id. Los factores por categoría y `compare` siguen siendo B4.)
**Archivos afectados**:
- [agent_tools.py](backend/app/services/agent_tools.py) —
  - `_cotizar` ([:219-226](backend/app/services/agent_tools.py#L219-L226)): usa
    `ctx.recommendation["product_id"]` si existe (fallback `"hogar-estandar"` si el
    LLM cotiza sin recomendar antes) y devuelve ese `product_id`.
  - `_ajustar_comparar` ([:285](backend/app/services/agent_tools.py#L285)): resuelve
    los `ajustes_disponibles` del producto recomendado, no de hogar fijo.
  - Descripción de la tool `cotizar`: deja de decir "seguro de hogar".
- [conversation.py](backend/app/services/conversation.py#L95-L128) — `update_profile`:
  `product_name` desde `self._catalog.get_product(product_id)` (patrón ya usado en
  [orchestrator.py:176-183](backend/app/services/orchestrator.py#L176-L183)),
  cotización con `product_id=propensity_result["product_id"]` y mensaje con el nombre
  dinámico. `apply_adjustments` ([:258](backend/app/services/conversation.py#L258)):
  valida códigos contra el producto de `session.recommendation.product_id`.
- Tests (ampliar `tests/test_agent_tools.py` y e2e):
  - tools: perfil con `has_vehicle` → `recomendar_seguro` devuelve `movilidad-auto` y
    `cotizar` cotiza ESE producto (mensual $120.000 con perfil neutro 36-45, cifra de
    B2); `ajustar_comparar` lista ajustes de movilidad (`zero_deductible`…).
  - `cotizar` sin recomendación previa → sigue cotizando hogar (fallback, sin error).
  - e2e REST nuevo: `POST /profile` con `has_credit=True` (41-55, sin propiedad) →
    `recommendation.product_id == "credito-vida-deudor"`, `product_name` del catálogo
    y `quote.monthly_premium` del producto de crédito; consent cierra con ese id.
  - Ruta negativa: ajuste de otro producto en `apply_adjustments` → 4xx (ya existe la
    validación; se fija con el producto dinámico).
  - [test_e2e_happy_path.py](backend/tests/test_e2e_happy_path.py) intacto (perfil
    casa → hogar a $3.750/mes como siempre).

**Impacto en contrato API (front↔back)**: Sí — **sin cambio de shape**: mismas rutas,
mismos campos, mismos status codes; lo que cambia son los **valores** —
`recommendation.product_id/product_name` y la cotización ya no son siempre de hogar.
El frontend (tarjetas D3, resumen D4) ya renderiza esos campos dinámicamente desde el
payload → **ningún cambio de frontend requerido**; verificarlo en el smoke manual del
checkpoint. Quien consuma el demo debe saber que el guion multicategoría (H4) ya
puede mostrarse.
**Acciones**:
1. TDD-light: tests de coherencia primero (rojos: cotizar devuelve hogar tras
   recomendar movilidad).
2. Cablear `product_id` en `_cotizar`, `_ajustar_comparar`, `update_profile` y
   `apply_adjustments`.
3. Suite completa verde.

**Pruebas / verificación**: pytest completo verde. Smoke manual sin LLM: `uvicorn` +
`POST /api/v1/conversations` + `/profile` con `{"has_vehicle": true, "age_range":
"26-40"}` → recomendación Movilidad con su prima; y con el perfil casa clásico → Hogar
$3.750/mes intacto. Con LLM (si hay quota de Gemini): conversación "tengo carro" →
recomendación y cotización de Auto coherentes.
**Riesgos**: algún test de tarjetas/handoff que asuma hogar en fixtures propios — no
se detectó ninguno acoplado al flujo (los 7 archivos que citan "Hogar Estándar" arman
sus propios datos), pero si la suite lo revela, se ajusta el fixture, nunca la
validación. LLM cotizando sin recomendar → cubierto por el fallback testeado.

🛑 **CHECKPOINT** — fin del plan.
**Commit sugerido**: `feat(back): quote and close on the recommended product`

---

## Deuda / fuera de alcance (anotada para el vault)

- **A4**: persistencia del perfil enriquecido en Postgres (tabla
  `perfil_enriquecido`) y tool `enriquecer_perfil` genérica — B3 deja los campos
  viajando en sesión; A4 los hace sobrevivir reinicios.
- **B4**: factores por categoría desde el JSON del catálogo (hoy documentales; el
  ×1.15 de edad sigue global) y `compare` de 2 variantes lado a lado.
- **B5**: preguntas por categoría según la Matriz (el system prompt del orquestador
  sigue hogar-céntrico en su primer párrafo — se reescribe con el guion H4/B5, no
  aquí).
- **Mascotas**: sexta categoría solo si sobra tiempo (nota del vault) — sería 1
  producto en el JSON + ~2 reglas en `CATEGORY_RULES` (`has_pets`).
- **Calibración fina con la base real completa** (1,5M registros): cuando C2 cargue
  conteos reales, las evidencias citables se actualizan en `CATEGORY_RULES` sin tocar
  el motor.
