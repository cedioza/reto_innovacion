# Plan — B2: Catálogo de las 4 categorías restantes · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-25 · **Tipo**: plan de implementación por fases.
> **Base**: [20260725-b1-catalogo-multiproducto-json.plan.md](.claude/analysis/plans/20260725-b1-catalogo-multiproducto-json.plan.md)
> (catálogo en JSON versionado con carga validada — B1 garantizó "producto nuevo =
> editar JSON, cero código"; este plan es la prueba de fuego de esa promesa) y
> [20260725-e1-handoff-correo-aseguradora-simulada.plan.md](.claude/analysis/plans/20260725-e1-handoff-correo-aseguradora-simulada.plan.md)
> (`INSURER_BY_PRODUCT` con fallback — se amplía aquí para coherencia del demo).
> Tarea del vault: `07 - Tareas/Feature B - Catalogo y motores/B2 - Catalogo de las 4 categorias restantes.md`
> (depende de **B1 ✅** ya en master; **bloquea H4**).
> **Proyectos afectados**: backend.
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

`backend/app/data/catalogo/productos.json` pasa de 1 a **5 productos** — Hogar (B1),
**Accidentes Personales**, **Vida**, **Movilidad (auto)** y **Crédito (vida
deudor)** — cada uno con coberturas, exclusiones (ninguno sin exclusiones: es lo que
da credibilidad en la conversación), 2–3 ajustes y tarifas verosímiles coherentes
con los guiones del demo. Además, `cotizar()` puede calcular precio para **cualquier**
producto del catálogo (test paramétrico), no solo hogar.

Criterios de aceptación del vault:
1. Las 5 categorías cargan y `cotizar()` devuelve precio para cada una (test
   paramétrico).
2. Ningún producto sin exclusiones.

## Contexto / hallazgos del análisis

**B1 dejó el terreno listo — agregar productos es editar JSON:**

- [productos.json](backend/app/data/catalogo/productos.json) — array validado con
  `TypeAdapter(list[Product])` al cargar
  ([catalog.py:19-33](backend/app/repositories/catalog.py#L19-L33)); hoy solo
  `hogar-estandar`. El test dummy de B1 (`test_catalog_json.py`) ya probó que un
  producto de otra categoría carga sin tocar código.
- Ningún test fija el número de productos del catálogo (verificado:
  [test_catalog.py:37-38](backend/tests/test_catalog.py#L37-L38) asserta `>= 1`) —
  agregar productos no rompe nada existente.

**⚠️ Semántica de `base_price`: es prima ANUAL, no mensual.** El motor hace
`annual_premium = base_price × factores` y `monthly = annual / 12`
([quote.py:51-53](backend/app/services/quote.py#L51-L53)); hogar: 45.000 anual →
$3.750/mes. Los guiones hablan en MENSUAL → los `base_price` nuevos van
multiplicados ×12 (tabla abajo). Errarle aquí infla/desinfla la tarifa 12×.

**El único hueco de código para el criterio 1:**
[QuoteService.calculate_quote](backend/app/services/quote.py#L18-L23) hardcodea
`get_product("hogar-estandar")`. Se agrega un parámetro **aditivo**
`product_id: str = "hogar-estandar"` — los 4 callers actuales
([quote router](backend/app/api/routes/), [conversation.py:101](backend/app/services/conversation.py#L101),
[agent_tools](backend/app/services/agent_tools.py), [conversation.py:208](backend/app/services/conversation.py#L208))
no cambian. Nota: el factor de edad del motor sigue hardcodeado (1.15 para
18-25/65+, [quote.py:29-33](backend/app/services/quote.py#L29-L33)) y se aplica a
TODOS los productos por igual — mover los factores del JSON al motor es **B4**, no
B2 (los `factors` del JSON siguen documentales, igual que en B1).

**Tarifas y aseguradoras — fuente: guiones del demo (vault):**
`Guiones de Demo Conversacional (MVP)`: Accidentes **$5.000/mes** (Seguros Sura),
Vida **$15.000/mes** (Seguros Bolívar), Auto **$120.000/mes** (Mapfre), Crédito
vida deudor **$25.000/mes** (Aseguradora Solidaria). Los flujos auditados
(`Flujo Actual Personal y Familiar/Movilidad/Crédito`) aportan las subcategorías
reales (Accidentes con Metlife/Chubb; Movilidad: carros/motos/SOAT; Crédito: vida
deudor/desempleo con Panamerican Life/Sura).

**Coherencia del handoff (E1):**
[handoff.py:14-28](backend/app/services/handoff.py#L14-L28) — `INSURER_BY_PRODUCT`
solo mapea `hogar-estandar → "Seguros Bolívar"`; los ids nuevos caerían al fallback
"la aseguradora aliada". Ampliar el mapa con las aseguradoras de los guiones es
aditivo y mantiene chat/correo/página diciendo lo mismo
([test_handoff.py:81-82](backend/tests/test_handoff.py#L81-L82) usa `producto-x`
para el fallback — sigue verde).

**Decisiones resueltas en el análisis:**

1. **Mascotas queda fuera** (nota explícita del vault: solo si sobra tiempo; no está
   en los guiones). Anotada en deuda.
2. **Un producto por categoría nueva** (el estándar de cada una): ids
   `accidentes-personales`, `vida-basico`, `movilidad-auto`, `credito-vida-deudor`;
   `category` en minúsculas sin tilde: `accidentes`, `vida`, `movilidad`, `credito`
   (consistente con `hogar`; los `name` sí llevan tildes). Variantes (moto, plan
   familiar, codeudor) se modelan como **ajustes** o **factores documentales**, no
   como productos aparte.
3. **La recomendación/conversación NO cambia**: `PropensityService` y el orquestador
   siguen recomendando hogar (multicategoría es B3/B5). B2 solo garantiza que el
   catálogo y el motor puedan cotizar las 5 — el test paramétrico llama a
   `QuoteService` directo.
4. **Datos de los productos definidos en este plan** (tabla abajo) para que la
   ejecución no dependa del vault. Perfil neutro (36-45) → el mensual queda EXACTO a
   los guiones.

**Datos a cargar (resumen ejecutable; coberturas/exclusiones con nombre +
descripción como las de hogar):**

| Campo | accidentes-personales | vida-basico | movilidad-auto | credito-vida-deudor |
|---|---|---|---|---|
| name | Accidentes Personales | Vida Básico | Auto Todo Riesgo | Crédito Vida Deudor |
| category | accidentes | vida | movilidad | credito |
| base_price (ANUAL) | 60000.0 | 180000.0 | 1440000.0 | 300000.0 |
| → mensual sin ajustes | $5.000 | $15.000 | $120.000 | $25.000 |
| coverages (4-5) | Gastos médicos por accidente; Muerte accidental; Incapacidad total o permanente; Renta diaria por hospitalización | Muerte por cualquier causa; Incapacidad total y permanente; Enfermedades graves (anticipo); Auxilio funerario; Auxilio educativo para hijos | Responsabilidad civil extracontractual; Pérdida total por daños o hurto; Pérdida parcial; Asistencia en carretera y grúa; Conductor elegido | Fallecimiento salda la deuda; Incapacidad total y permanente; Desempleo involuntario (hasta 3 cuotas); Enfermedades graves (anticipo de saldo) |
| exclusions (3-4) | Enfermedad general (no es seguro de salud); Accidentes bajo alcohol o sustancias; Deportes extremos no declarados; Autolesiones | Suicidio en el primer año; Preexistencias no declaradas; Actividades de alto riesgo no declaradas; Guerra o conflicto armado | Conductor sin licencia vigente; Conducción en embriaguez; Uso comercial no declarado (plataformas); Competencias o carreras | Preexistencias no declaradas; Suicidio en el primer año; Renuncia voluntaria o despido con justa causa (desempleo); Guerra o conflicto armado |
| adjustments (2-3, code / modifier) | extreme_sports 1.30; family_plan 1.75; higher_medical 1.20 | double_capital 1.80; critical_illness_plus 1.35; funeral_assist 1.10 | zero_deductible 1.25; replacement_car 1.15; low_mileage 0.90 | unemployment_plus 1.20; joint_debtor 1.60 |
| factors (documentales hasta B4) | age_range: 18-25→1.10, 60+→1.20 | age_range: 18-25→0.85, 26-35→0.95, 36-45→1.0, 46-60→1.35, 60+→1.80 | vehicle_type: auto→1.0, moto→0.65; age_range: 18-25→1.30 | age_range: 46-60→1.25, 60+→1.60; debt_balance: <50M→0.60, 50-150M→1.0, >150M→1.50 |
| aseguradora (handoff) | Seguros Sura | Seguros Bolívar | Mapfre | Aseguradora Solidaria |

(Etiqueta "(simulación)" del correo/página ya la pone E1; los nombres de
aseguradoras son simulados para el pitch, como dicen los guiones.)

## Decisiones pendientes (bloqueantes)

(ninguna — tarifas y aseguradoras salen de los guiones ya socializados; Mascotas
excluida por nota del propio vault.)

## Principios

- Es la prueba de la promesa de B1: **la Fase 1 no toca código Python** — solo JSON
  + tests. Si algo de código hiciera falta para cargar, es un bug de B1.
- `base_price` SIEMPRE anual (×12 del mensual de los guiones) — verificado por test.
- Contrato intacto: `calculate_quote` gana un parámetro con default; ningún caller,
  firma pública ni shape de respuesta cambia. Los tests de cifras existentes
  ($3.750/45.000) siguen pasando sin editarse.
- Ningún producto sin exclusiones ni sin coberturas (test paramétrico sobre TODO el
  catálogo, no lista fija — cubre también productos futuros).
- Cero dependencias nuevas, cero env vars nuevas. TDD-light.

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | ambos | Ninguno | 5m | _(sin commit)_ |
| 1 | 4 productos nuevos en el JSON + tests de estructura | backend | Aditivo (solo datos) | 30m | `feat(back): add 4 insurance categories to product catalog` |
| 2 | `cotizar()` por producto + aseguradoras del handoff | backend | Aditivo | 30m | `feat(back): quote any catalog product and map its insurer` |

Total: ~65m. (H4 —guion multicategoría— queda desbloqueada; B3/B5 construyen sobre
`category`.)

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: ambos
**Objetivo**: punto de partida verde.
**Archivos afectados**: ninguno.
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Backend desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` → línea base
   (276 passed + 9 skipped si D4 ya está en master; registrar la que aparezca).
2. Frontend desde `frontend/`: `npm run build` → OK (no se toca; solo registro).

**Pruebas / verificación**: las de arriba.
**Riesgos**: ninguno.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit)_

---

## Fase 1 — 4 productos nuevos en el JSON + tests de estructura

**Proyecto**: backend
**Objetivo**: el catálogo contiene las 5 categorías con datos verosímiles; ningún
producto sin exclusiones. **Cero código Python de producción** (la promesa de B1).
**Archivos afectados**:
- [productos.json](backend/app/data/catalogo/productos.json) — se agregan los 4
  objetos de la tabla de arriba (mismo shape que hogar: `id`, `name`, `description`,
  `category`, `coverages[{name,description}]`, `exclusions[{name,description}]`,
  `adjustments[{code,name,description,premium_modifier}]`, `base_price` ANUAL,
  `currency: "COP"`, `factors`). Descripciones en una línea, tono del catálogo de
  hogar. UTF-8 sin BOM, indent 2.
- Tests nuevos (`tests/test_catalog_multiproduct.py`):
  - carga: `list_products()` devuelve **≥ 5** y contiene exactamente los ids
    `hogar-estandar`, `accidentes-personales`, `vida-basico`, `movilidad-auto`,
    `credito-vida-deudor`;
  - paramétrico sobre `list_products()` COMPLETO (criterio 2): todo producto tiene
    `exclusions` no vacías, `coverages` no vacías, 2–3+ `adjustments` con
    `premium_modifier` numérico > 0, `category` no vacía y `currency == "COP"`;
  - `category` correcta por id (las 5 distintas);
  - tarifas anuales exactas por id: 60000 / 180000 / 1440000 / 300000 (y hogar
    45000 intacto).

**Impacto en contrato API (front↔back)**: No — nada expuesto cambia (la
recomendación sigue siendo hogar; los productos nuevos aún no viajan en ninguna
respuesta).
**Acciones**:
1. TDD-light: tests primero (rojos: los ids no existen).
2. Editar el JSON con los 4 productos de la tabla.
3. Suite completa verde (los tests de B1 y de cifras intactos).

**Pruebas / verificación**: pytest completo verde; validación implícita del JSON por
`TypeAdapter` al primer uso (si un campo quedó mal tipado, la suite entera lo grita).
**Riesgos**: deriva de semántica anual/mensual en `base_price` → mitigada por el
test de tarifas anuales exactas; typo en el JSON → lo captura la validación de B1.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `feat(back): add 4 insurance categories to product catalog`

---

## Fase 2 — `cotizar()` por producto + aseguradoras del handoff

**Proyecto**: backend
**Objetivo**: el motor cotiza cualquier producto del catálogo (criterio 1) y el
handoff conoce la aseguradora de cada categoría (coherencia chat/correo del demo).
**Archivos afectados**:
- [quote.py](backend/app/services/quote.py) — `calculate_quote(profile,
  selected_adjustments=None, product_id: str = "hogar-estandar")`: reemplaza el
  literal de [quote.py:23](backend/app/services/quote.py#L23) por el parámetro.
  Nada más cambia (el factor de edad hardcodeado se queda — es B4). Callers
  intactos (usan el default).
- [handoff.py](backend/app/services/handoff.py) — `INSURER_BY_PRODUCT` gana:
  `accidentes-personales → "Seguros Sura"`, `vida-basico → "Seguros Bolívar"`,
  `movilidad-auto → "Mapfre"`, `credito-vida-deudor → "Aseguradora Solidaria"`.
- Tests (ampliar `tests/test_catalog_multiproduct.py`):
  - **criterio 1 paramétrico**: para cada uno de los 5 ids, `calculate_quote`
    con perfil neutro (`age_range="36-45"`) devuelve `monthly_premium` > 0 e
    IGUAL al mensual de los guiones: 3750 / 5000 / 15000 / 120000 / 25000;
  - con perfil 18-25 el mensual sube ×1.15 en cualquier producto (comportamiento
    actual del motor, documentado hasta B4);
  - ajuste propio de un producto nuevo (p. ej. `low_mileage` en movilidad-auto:
    120000 × 0.90 = 108000/mes) aplica su modifier; un código de OTRO producto
    (p. ej. `fire_alarm` en vida-basico) se ignora sin error (comportamiento
    actual: ajuste desconocido no aplica);
  - producto inexistente → `ValueError("Product not found")` (ruta negativa del
    service, ya existente — se fija con test);
  - `insurer_for` de cada id nuevo devuelve su aseguradora y `producto-x` sigue en
    fallback (el test existente no se toca).

**Impacto en contrato API (front↔back)**: No — parámetro interno con default;
ninguna ruta/shape/env var visible cambia. (Cuando B3/B4 expongan multicategoría en
la conversación, ahí sí habrá contrato nuevo — fuera de B2.)
**Acciones**:
1. TDD-light: tests primero (rojo: `calculate_quote` no acepta `product_id`).
2. Implementar parámetro + mapa de aseguradoras.
3. Suite completa verde.

**Pruebas / verificación**: pytest completo verde (línea base + nuevos, cero tests
existentes editados). Manual opcional (no requiere LLM): `uvicorn` +
`POST /api/v1/conversations` + `/profile` → la cotización de hogar sigue en
$3.750/mes (default intacto).
**Riesgos**: ninguno relevante — cambio de 2 líneas + datos; la suite de cifras
protege el default.

🛑 **CHECKPOINT** — fin del plan.
**Commit sugerido**: `feat(back): quote any catalog product and map its insurer`

---

## Deuda / fuera de alcance (anotada para el vault)

- **Mascotas**: en la Matriz pero no en los guiones — solo si sobra tiempo (nota del
  vault). Sería 1 objeto más en el JSON + 1 fila en `INSURER_BY_PRODUCT`.
- **B4**: mover los `factors` del JSON al motor (hoy documentales; el factor de edad
  1.15 sigue hardcodeado e igual para todos los productos) y des-hardcodear
  `"hogar-estandar"` en los callers de conversación/tools.
- **B3/B5**: propensión y preguntas multicategoría — la recomendación sigue siendo
  hogar hasta entonces; `category` ya queda poblada para ambas.
- Subcategorías reales de los flujos (moto como producto propio, desempleo de
  crédito, SOAT) → variantes futuras si el pitch las pide; hoy quedan como factores
  o coberturas documentales.
