# Plan — B1: Estructura de catálogo multi-producto en JSON · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-25 · **Tipo**: plan de implementación por fases.
> **Base**: [20260724-remediacion-violaciones-reglas-backend.plan.md](.claude/analysis/plans/20260724-remediacion-violaciones-reglas-backend.plan.md)
> (fijó las capas `api → services → repositories → models` que este plan respeta).
> Tarea del vault: `07 - Tareas/Feature B - Catalogo y motores/B1 - Estructura de catalogo multiproducto.md`
> (sin dependencias; **bloquea B2, B3, B4 y B5** — toda la Feature B).
> **Proyectos afectados**: backend.
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

El catálogo pasa de un producto hardcodeado en Python
([catalog.py:12-82](backend/app/repositories/catalog.py#L12-L82), solo
`hogar-estandar`) a un **JSON versionado en el repo** con esquema común por categoría
(id, nombre, categoría, coberturas, exclusiones, ajustes, tarifa base, factores),
cargado y validado por el mismo `CatalogRepository`. Hogar migra como primer producto
**sin romper nada** (mismos valores al byte). Agregar un producto nuevo = editar JSON,
cero código — es lo que B2 hará con las 4 categorías restantes.

Criterios de aceptación del vault:
1. `list_products()` devuelve Hogar desde JSON y los tests existentes pasan sin
   cambios de contrato.
2. Agregar un producto nuevo = editar JSON, cero código (test que carga un dummy).

## Contexto / hallazgos del análisis

**El contrato del catálogo es mínimo y estable** — la migración es de bajo riesgo:

- Consumidores: TODOS usan solo `get_product(product_id)` y `list_products()` vía
  `CatalogService` ([catalog.py service](backend/app/services/catalog.py)):
  [quote.py:23](backend/app/services/quote.py#L23), agent_tools
  ([284](backend/app/services/agent_tools.py#L284) y
  [343](backend/app/services/agent_tools.py#L343)), orchestrator
  ([172](backend/app/services/orchestrator.py#L172), [451](backend/app/services/orchestrator.py#L451))
  y conversation ([197](backend/app/services/conversation.py#L197)). Nadie construye
  `Product` fuera del repositorio. El service y los callers **no se tocan**.
- [models/product.py](backend/app/models/product.py) — dataclasses (`Product`,
  `Coverage`, `Exclusion`, `Adjustment`). Nota: el vault dice "esquema Pydantic ya
  existe" pero en realidad son **dataclasses** — da igual para validar: pydantic (ya
  dependencia) valida dataclasses nativas con `TypeAdapter`, así el JSON malformado
  falla con error claro sin cambiar el tipo del modelo ni sus consumidores.
- [tests/test_catalog.py](backend/tests/test_catalog.py) — 6 tests de contrato
  (existencia de hogar, ≥3 coberturas/exclusiones, determinismo, None en desconocido,
  list ≥1). Criterio 1 = estos pasan sin editarse.

**⚠️ Dónde vive el JSON — desviación deliberada del vault:**

- El vault (`Stack y arquitectura`) pide carpeta `catalogo/` en la **raíz del
  monorepo**. Pero la app de Dokploy del backend se construye con **root `backend/`**
  (DEC-007/H1): un archivo fuera de `backend/` **no existe en la imagen desplegada**.
- Resolución: el JSON vive en **`backend/app/data/catalogo/productos.json`** — sigue
  siendo "JSON versionado en el repo" (el requisito real: fuente de verdad única,
  diffs revisables, NO en BD) y funciona en el deploy. Precedente en el propio repo:
  `afiliados.csv` vive en `backend/app/data/` con override por env var
  ([config.py:29](backend/app/core/config.py#L29), `AFFILIATE_CSV_PATH`). Se replica
  el patrón: `CATALOG_JSON_PATH` opcional.

**Sobre `category` y `factors` (estructura para B3/B4, sin lógica hoy):**

- El factor de edad hoy está hardcodeado en
  [quote.py:29-33](backend/app/services/quote.py#L29-L33) (`1.15` para 18-25/65+).
  B1 solo **da estructura**: `Product` gana `category: str` y `factors: dict`
  (libre, p. ej. `{"age_range": {"18-25": 1.15, "65+": 1.15}}`). El JSON de hogar
  documenta sus factores reales, pero `QuoteService` NO cambia en B1 — mover el
  motor a leer factores del catálogo es exactamente B4. Cero riesgo de doble fuente:
  hoy los factores del JSON son datos documentales; B4 los vuelve operativos.

**Decisiones resueltas en el análisis:**

1. **Ubicación**: `backend/app/data/catalogo/productos.json` (un solo archivo para
   las 5 categorías — B2 agrega objetos al array; con 5 productos un archivo por
   categoría es sobre-ingeniería). Override opcional `CATALOG_JSON_PATH` (patrón
   `AFFILIATE_CSV_PATH`).
2. **Validación con `pydantic.TypeAdapter(list[Product])`** sobre las dataclasses
   existentes — JSON inválido (campo faltante, tipo errado, modifier no numérico) →
   error claro al primer uso, no un producto silenciosamente cojo. Sin migrar los
   modelos a BaseModel (los consumidores usan atributos, nada cambia).
3. **Carga perezosa con caché a nivel de módulo por ruta** (los services instancian
   `CatalogRepository()` por llamada — p. ej. `QuoteService()` dentro de tools — y
   releer el disco cada vez es desperdicio): función `_load_products(path)` con
   `functools.lru_cache`; `CatalogRepository(path: str | None = None)` acepta ruta
   para que los tests carguen JSON temporal (criterio 2) sin tocar el default.
4. **Migración por igualdad, no por reescritura**: el JSON de hogar se genera con los
   MISMOS valores del dict actual (los tests de cifras de toda la suite — 3.750,
   45.000, modifiers 0.85/0.80/1.25 — son la red de seguridad).

## Decisiones pendientes (bloqueantes)

(ninguna — la ubicación del JSON queda resuelta arriba con su justificación de
deploy; si el equipo insiste en `catalogo/` raíz, es un `CATALOG_JSON_PATH` de
diferencia, no un rediseño.)

## Principios

- Contrato intacto: `get_product`/`list_products` no cambian de firma ni de tipo de
  retorno; los 6 tests de `test_catalog.py` pasan **sin editarse** (criterio 1).
- Migración por igualdad al byte: mismas cifras, mismos textos — la suite completa
  (241 tests, muchos con cifras literales) es la verificación.
- Aditivo antes que destructivo: primero el modelo extendido y el JSON + loader; el
  dict hardcodeado se elimina solo cuando el loader ya lo reemplazó en verde.
- Campos nuevos con default (`category`, `factors`) — nada existente se rompe.
- Env var nueva (`CATALOG_JSON_PATH`) → `Settings` + `.env.example` en la misma fase.
- Cero dependencias nuevas (pydantic ya está). TDD-light.

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | ambos | Ninguno | 5m | _(sin commit)_ |
| 1 | Modelo extendido + JSON de hogar + loader con validación | backend | Medio (interno) | 35m | `feat(back): load product catalog from versioned json` |

Total: ~40m. (Una sola fase de trabajo: el cambio es atómico — separar "modelo" de
"loader" dejaría una fase intermedia sin nada verificable. B2/B3/B4/B5 quedan
desbloqueadas al terminar.)

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: ambos
**Objetivo**: punto de partida verde.
**Archivos afectados**: ninguno.
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Backend desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` → línea base
   (241 passed + 9 skipped si D3 está mergeado; registrar la que aparezca).
2. Frontend desde `frontend/`: `npm run build` → OK (registro; no se toca).

**Pruebas / verificación**: las de arriba.
**Riesgos**: ninguno.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit)_

---

## Fase 1 — Modelo extendido + JSON de hogar + loader con validación

**Proyecto**: backend
**Objetivo**: el catálogo completo (hoy: hogar) vive en JSON versionado; el
repositorio lo carga, valida y cachea; agregar productos deja de requerir código.
**Archivos afectados**:
- [models/product.py](backend/app/models/product.py) — `Product` gana
  `category: str = "hogar"` y `factors: dict = field(default_factory=dict)`.
- `backend/app/data/catalogo/productos.json` (nuevo) — array con `hogar-estandar`
  migrado con los MISMOS valores de
  [catalog.py:12-82](backend/app/repositories/catalog.py#L12-L82) (5 coberturas, 4
  exclusiones, 3 ajustes con modifiers 0.85/0.80/1.25, base 45.000, currency COP) +
  los campos nuevos: `"category": "hogar"` y
  `"factors": {"age_range": {"18-25": 1.15, "65+": 1.15}}` (documentales hasta B4 —
  espejo de [quote.py:29-33](backend/app/services/quote.py#L29-L33)).
- [repositories/catalog.py](backend/app/repositories/catalog.py) — el dict
  hardcodeado se reemplaza por: `_load_products(path)` module-level con
  `functools.lru_cache` que lee el JSON y lo valida con
  `pydantic.TypeAdapter(list[Product])` (error claro si el JSON está roto);
  `CatalogRepository(path: str | None = None)` usa `settings.catalog_json_path` o el
  default `app/data/catalogo/productos.json` (ruta resuelta relativa al paquete, no
  al cwd — mismo criterio que el CSV de afiliados); `get_product`/`list_products`
  idénticos en firma y comportamiento.
- [core/config.py](backend/app/core/config.py) — `catalog_json_path: str = ""`.
- [.env.example](backend/.env.example) — `CATALOG_JSON_PATH=` documentada (default:
  el JSON del repo).
- Tests nuevos (`tests/test_catalog_json.py`):
  - **criterio 2**: JSON temporal (tmp_path) con un producto dummy de otra categoría
    → `CatalogRepository(path=...)` lo devuelve por `get_product`/`list_products`
    sin tocar código;
  - paridad de migración: el hogar cargado desde el JSON real tiene las mismas
    cifras/estructura que esperan los tests de cifras (3.750/45.000, 3 ajustes);
  - `category`/`factors` presentes en el producto cargado;
  - JSON inválido (campo requerido faltante / modifier string) → excepción clara, no
    un producto a medias;
  - determinismo: dos repos sobre la misma ruta devuelven los mismos datos (caché).
- Tests existentes: [test_catalog.py](backend/tests/test_catalog.py) **sin editar**
  (criterio 1); el resto de la suite (cifras del motor por todos lados) tampoco.

**Impacto en contrato API (front↔back)**: No — cambio interno del backend; ninguna
ruta, shape ni env var que el front vea. (`factors`/`category` podrían aparecer en
payloads futuros vía B4/D3, no hoy.)
**Acciones**:
1. TDD-light: `tests/test_catalog_json.py` primero (fallan: no existe el JSON, ni el
   path param, ni los campos nuevos — razón correcta).
2. Modelo + JSON + loader + Settings + `.env.example`.
3. Suite completa verde (los 6 de `test_catalog.py` intactos incluidos).

**Pruebas / verificación**: pytest completo verde (línea base + nuevos, cero tests
existentes editados); manual rápido: levantar uvicorn y correr un
`POST /api/v1/conversations` + `POST .../profile` → la cotización sigue dando
$3.750/mes (el motor leyó el catálogo desde JSON); opcional: romper el JSON a
propósito en local → el arranque/primer uso falla con error legible, restaurar.
**Riesgos**: ruta relativa al cwd (uvicorn se lanza desde `backend/`, pytest también,
pero Dokploy puede variar) → mitigado resolviendo la ruta desde `__file__` del
paquete; deriva de valores en la migración → mitigada por la suite de cifras; el
`lru_cache` retiene el JSON entre tests que usan la MISMA ruta — los tests de dummy
usan rutas tmp distintas, sin colisión.

🛑 **CHECKPOINT** — fin del plan.
**Commit sugerido**: `feat(back): load product catalog from versioned json`

---

## Deuda / fuera de alcance (anotada para el vault)

- **B2**: las 4 categorías restantes = agregar objetos al `productos.json` con
  tarifas verosímiles del portafolio público de colsubsidio.com (cero código — este
  plan lo garantiza con el test dummy).
- **B4**: mover el factor de edad (y los que vengan por categoría) de
  `QuoteService` a los `factors` del catálogo, y des-hardcodear `"hogar-estandar"`
  en [quote.py:23](backend/app/services/quote.py#L23) y
  [agent_tools.py:284](backend/app/services/agent_tools.py#L284).
- **B3/B5**: propensión multicategoría y preguntas por categoría construyen sobre
  `category`.
- Si el equipo quiere el `catalogo/` en la raíz del monorepo como pide el vault
  literal: basta apuntar `CATALOG_JSON_PATH` en dev y ajustar el build de Dokploy
  (montar el archivo) — anotado como alternativa, no recomendada para el domingo.
