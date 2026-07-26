# Plan — B4: Cotizador multi-categoría con ajustar y comparar · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-25 · **Tipo**: plan de implementación por fases.
> **Base**: [20260725-b1-catalogo-multiproducto-json.plan.md](.claude/analysis/plans/20260725-b1-catalogo-multiproducto-json.plan.md)
> (estructura `Product` con `category` y `factors`),
> B2 (catálogo de 5 categorías con `factors` por producto, mergeado hoy) y
> B3 (propensión multicategoría, mergeado hoy — **ya parametrizó `product_id` en el
> cotizador y ancló las tools al producto recomendado**). Tarea del brain:
> **B4 — Cotizador multi-categoría con ajustar y comparar** (Feature B, depende de B1 ✔).
> **Proyectos afectados**: backend.
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

`QuoteService` cotiza cualquier producto del catálogo aplicando los **factores de su
categoría definidos en el catálogo** (hoy ignora `product.factors` y usa un multiplicador
de edad hardcodeado), y expone **`compare`** — dos cotizaciones lado a lado con sus
diferencias marcadas — como primitiva única que reutilizan la tool `ajustar_comparar`
(A2) y el endpoint REST de ajustes. Es el frente 3 del "buen resultado" oficial:
ajustar, comparar, resolver dudas.

## Contexto / hallazgos del análisis

**Lo que B3 ya dejó hecho (no repetir):**

- [quote.py:18-23](backend/app/services/quote.py#L18-L23) — `calculate_quote(profile,
  selected_adjustments, product_id="hogar-estandar")` ya acepta `product_id`.
- Todos los callers ya pasan el producto recomendado: la tool `cotizar`
  ([agent_tools.py:252](backend/app/services/agent_tools.py#L252)), la tool
  `ajustar_comparar` ([agent_tools.py:310](backend/app/services/agent_tools.py#L310)),
  `update_profile` ([conversation.py:107](backend/app/services/conversation.py#L107)) y
  `apply_adjustments` ([conversation.py:261-275](backend/app/services/conversation.py#L261-L275)).

**La brecha real de B4:**

1. **Factores hardcodeados e inconsistentes con el catálogo**:
   [quote.py:30-34](backend/app/services/quote.py#L30-L34) aplica un único multiplicador
   de edad fijo (`1.15` si `age_range in ("18-25", "65+")`) **para todos los productos**,
   ignorando `product.factors`, que B2 ya pobló por categoría:
   - `hogar-estandar`: `age_range {"18-25": 1.15, "65+": 1.15}`
   - `accidentes-personales`: `age_range {"18-25": 1.1, "60+": 1.2}`
   - `vida-basico`: `age_range` en 5 tramos (0.85 → 1.8)
   - `movilidad-auto`: `vehicle_type {auto, moto}` + `age_range {"18-25": 1.3}`
   - `credito-vida-deudor`: `age_range` + `debt_balance` en 3 tramos
   Hoy vida cuesta lo mismo a los 25 que a los 60 — el catálogo dice lo contrario.
2. **Bucket muerto "65+"**: los perfiles usan `"60+"` (ver
   [channel_handler.py:11-21](backend/app/services/channel_handler.py#L11-L21) y los
   factores de accidentes/vida/crédito), pero el factor de `hogar-estandar` en
   [productos.json](backend/app/data/catalogo/productos.json) dice `"65+"` — un valor
   que ningún perfil produce, o sea que hoy **ningún adulto mayor recarga en hogar** ni
   por código ni por catálogo. Alinear a `"60+"` es un cambio de comportamiento
   (hogar para 60+ pasa a 1.15×) — es la intención evidente del catálogo.
3. **Factores sin campo de perfil**: `vehicle_type` y `debt_balance` no existen en
   [ProfileData](backend/app/schemas/conversation.py#L28-L36) (B3 agregó solo flags
   `has_vehicle`/`has_credit`; los campos finos llegan con B5 — Preguntas por
   categoría). El motor debe tratarlos como **neutros (×1.0)** sin fallar.
4. **No existe `compare` como primitiva**: la lógica "actual vs propuesta +
   diferencia_mensual + ajustes_disponibles" está **duplicada** en
   [_ajustar_comparar (agent_tools.py:301-333)](backend/app/services/agent_tools.py#L301-L333)
   y en [apply_adjustments (conversation.py:251-297)](backend/app/services/conversation.py#L251-L297).
   B4 pide `compare` con las diferencias marcadas; centralizarla elimina la duplicación
   y garantiza que bot y panel muestren el mismo peso.

**Contratos que NO deben romperse:**

- El payload del mensaje `comparison` (`{actual, propuesta, diferencia_mensual,
  ajustes_disponibles}`) lo consume
  [CompareCard.vue](frontend/src/features/chat/components/CompareCard.vue) — claves
  nuevas son aditivas y no lo rompen; las existentes no cambian de nombre ni tipo.
- El shape de `calculate_quote` (claves `base_amount, adjustments, monthly_premium,
  annual_premium, currency, coverage_details, exclusions`) alimenta
  [QuoteDetail](backend/app/schemas/conversation.py#L45) — se mantiene.
- Redondeo actual: `round(x, 2)`, mensual = anual/12 redondeado — se mantiene
  (criterio: el peso del bot coincide con el del panel).

**Tests existentes afectados:**
[test_quote.py](backend/tests/test_quote.py) — `test_senior_age_increases_premium`
usa `age_range="65+"` (línea 63): al alinear el bucket pasa a `"60+"`. El resto
(fire_alarm, high_value, determinismo) sigue válido. `test_adjustments_endpoint.py`,
`test_agent_tools.py` (cotizar/ajustar_comparar) y `test_card_messages.py` cubren los
callers — no deberían cambiar si el contrato se preserva.

## Decisiones pendientes (bloqueantes)

(ninguna — resueltas en el análisis:)

- **Matching genérico de factores**: para cada `factors[nombre] = {bucket: mult}` se
  resuelve `getattr(profile, nombre, None)`; si el valor existe y está en los buckets
  → multiplica; si no (campo inexistente como `vehicle_type`, valor None, bucket no
  listado) → **neutro ×1.0**. Sin listas blancas en código: el catálogo manda.
- **Alinear `"65+"` → `"60+"`** en el factor de `hogar-estandar` (datos, no código),
  con el cambio de comportamiento documentado en el checkpoint.
- **`compare` vive en `QuoteService`** (motor determinista) y devuelve exactamente 2
  opciones (contrato de la tool A2: actual vs propuesta); el shape público de tool y
  endpoint no cambia — solo se agregan claves aditivas de diferencias.

## Principios

- Verde por fase: `.venv\Scripts\python.exe -m pytest -q` desde `backend/`.
- Contrato HTTP intacto: mismas rutas, mismos nombres/tipos de claves; solo aditivo.
- El catálogo es la fuente de verdad de precios y factores — cero números mágicos en
  código.
- Determinismo: mismos inputs → mismo peso, en bot, REST y panel.
- Cero dependencias nuevas; frontend no se toca.

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | backend | Ninguno | 5m | _(sin commit)_ |
| 1 | Factores por categoría desde el catálogo | backend | Medio | 30m | `feat(back): apply catalog factors per category in quotes` |
| 2 | `compare` como primitiva única del motor | backend | Aditivo | 30m | `feat(back): add quote compare with marked differences` |

Total estimado: ~65m (la estimación del brain para B4 es 3h — sobra margen porque B3
ya hizo la parametrización por producto).

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: backend
**Objetivo**: confirmar el punto de partida verde tras los merges de hoy (B2+B3+C1+C3).
**Archivos afectados**: ninguno (solo lectura).
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` (esperado: 378 passed,
   9 skipped).
2. Confirmar los factores actuales del catálogo (leer `productos.json`) y que ningún
   test aserta montos absolutos de hogar para perfiles 60+ (grep `65+` y `60+` en
   `backend/tests/`).
3. Confirmar el shape que consume `CompareCard.vue` (claves `actual`, `propuesta`,
   `diferencia_mensual`, `ajustes_disponibles`).
**Pruebas / verificación**: suite en verde; hallazgos anotados.
**Riesgos**: ninguno.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit — fase de solo lectura)_

---

## Fase 1 — Factores por categoría desde el catálogo

**Proyecto**: backend
**Objetivo**: el motor aplica los `factors` del producto (definidos en el catálogo)
en vez del multiplicador de edad hardcodeado; las 5 categorías cotizan con el mismo
contrato.
**Archivos afectados**:
[quote.py](backend/app/services/quote.py) ·
[productos.json](backend/app/data/catalogo/productos.json) (solo `"65+"` → `"60+"` en
hogar) ·
[test_quote.py](backend/tests/test_quote.py)
**Impacto en contrato API (front↔back)**: No — el shape del dict de cotización no
cambia; cambian montos donde el catálogo difiere del hardcode (intención de B2/B4).
**Acciones**:
1. En `calculate_quote`, reemplazar el bloque de edad hardcodeado
   ([quote.py:30-34](backend/app/services/quote.py#L30-L34)) por la aplicación
   genérica de `product.factors`: por cada `nombre → buckets`, tomar
   `getattr(profile, nombre, None)` y multiplicar por `buckets.get(valor, 1.0)`
   (valor None o bucket ausente → 1.0). El multiplicador combinado se aplica sobre
   `base_price` (mismo lugar donde hoy entra `age_multiplier`); redondeo intacto.
2. En `productos.json`, corregir el bucket muerto de hogar: `"65+"` → `"60+"`
   (datos alineados con los tramos reales de `ProfileData`/canales).
3. Tests (TDD-light: primero, en rojo por la razón correcta):
   - **Paramétrico de 5 categorías** (criterio 1): `pytest.mark.parametrize` sobre
     los 5 `product_id` → `calculate_quote` devuelve el contrato completo (mismas
     claves, montos > 0, mensual = anual/12 redondeado).
   - Factores del catálogo mandan: vida a los 60+ cuesta 1.8× lo de 36-45; moto
     (factor `vehicle_type` sin campo en el perfil) cotiza **neutro** sin excepción;
     hogar a los 60+ ahora recarga 1.15 (el bucket corregido).
   - Determinismo por categoría (mismo perfil dos veces → mismo peso).
   - Actualizar `test_senior_age_increases_premium` a `age_range="60+"`.
4. Correr la suite completa — los callers (tools, conversación, endpoint de ajustes)
   no cambian de código, solo de montos donde el catálogo difiere.
**Pruebas / verificación**: pytest en verde; caso negativo ya cubierto: producto
inexistente → `ValueError` ("Product not found") que los callers traducen a 4xx,
nunca 500.
**Riesgos**: cambio de montos en hogar para 60+ (documentado; era la intención del
catálogo); si algún test e2e asertaba montos exactos de hogar, se actualiza el monto
esperado — nunca se debilita la aserción.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `feat(back): apply catalog factors per category in quotes`

---

## Fase 2 — `compare` como primitiva única del motor

**Proyecto**: backend
**Objetivo**: `QuoteService.compare` devuelve 2 cotizaciones lado a lado con sus
diferencias marcadas, y la tool `ajustar_comparar` y `apply_adjustments` la reutilizan
(hoy duplican la lógica) — mismo peso en bot, REST y panel.
**Archivos afectados**:
[quote.py](backend/app/services/quote.py) ·
[agent_tools.py](backend/app/services/agent_tools.py) (`_ajustar_comparar`) ·
[conversation.py](backend/app/services/conversation.py) (`apply_adjustments`) ·
[test_quote.py](backend/tests/test_quote.py) ·
`backend/tests/test_adjustments_endpoint.py` / `test_agent_tools.py` (solo si algún
assert requiere las claves nuevas)
**Impacto en contrato API (front↔back)**: **Sí (aditivo)** — el payload del mensaje
`comparison` y el resultado de la tool `ajustar_comparar` conservan
`actual/propuesta/diferencia_mensual/ajustes_disponibles` y ganan claves de
diferencias marcadas (p. ej. `diferencia_anual`, `ajustes_activados`/`ajustes_retirados`).
[CompareCard.vue](frontend/src/features/chat/components/CompareCard.vue) no necesita
cambios (ignora claves extra); si luego se quiere pintar el detalle, es tarea de
frontend aparte.
**Acciones**:
1. `QuoteService.compare(profile, product_id, adjustments_a, adjustments_b) -> dict`:
   calcula ambas variantes con `calculate_quote` y devuelve
   `{actual, propuesta, diferencia_mensual, diferencia_anual, ajustes_activados,
   ajustes_retirados, ajustes_disponibles}` — las diferencias marcadas del criterio 3
   (deltas redondeados a 2 decimales; listas de códigos que entran/salen entre A y B).
2. Refactor `_ajustar_comparar` ([agent_tools.py:301-333](backend/app/services/agent_tools.py#L301-L333)):
   delega en `compare` usando los ajustes de la cotización actual (`ctx.quote`) como
   variante A y los pedidos como variante B; conserva la semántica actual
   (`ctx.quote` queda en la propuesta).
3. Refactor `apply_adjustments` ([conversation.py:272-297](backend/app/services/conversation.py#L272-L297)):
   misma delegación; el mensaje `comparison` se arma desde el resultado de `compare`
   (upsert del mensaje intacto). La validación de códigos desconocidos → `ValueError`
   → 400 se mantiene.
4. Tests (TDD-light):
   - `compare` devuelve 2 cotizaciones del mismo producto con `diferencia_mensual`
     y `diferencia_anual` consistentes (`propuesta - actual`, determinista) y las
     listas de ajustes que difieren (criterios 2 y 3).
   - Ajustar es determinista: aplicar y quitar el mismo ajuste vuelve al peso
     original exacto (criterio 2).
   - Paramétrico: `compare` funciona en las 5 categorías con sus propios códigos de
     ajuste (p. ej. `zero_deductible` en movilidad, `double_capital` en vida).
   - Negativo: código de ajuste desconocido en el endpoint REST → 400, nunca 500
     (ya existe — verificar que sigue verde).
**Pruebas / verificación**: pytest completo en verde; manual opcional: `POST
/api/v1/conversations/{id}/adjustments` y verificar que la tarjeta de comparación
del chat sigue pintando (claves viejas intactas).
**Riesgos**: `_sync_ctx_to_session` y `_append_card_messages` del orquestador leen
`diferencia_mensual` del resultado de la tool ([orchestrator.py:491-506](backend/app/services/orchestrator.py#L491-L506))
— la clave se conserva; el refactor no toca el orquestador.

🛑 **CHECKPOINT FINAL** — Con esto B4 cumple sus 3 criterios: cotiza las 5 categorías
con el mismo contrato (test paramétrico), ajustar recalcula determinista, y `compare`
devuelve 2 cotizaciones con diferencias marcadas. Marcar B4 en el brain.
**Commit sugerido**: `feat(back): add quote compare with marked differences`
