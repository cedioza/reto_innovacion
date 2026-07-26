# Plan — C2: Base de afiliados en Postgres (+ complemento sintético) · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-25 · **Tipo**: plan de implementación por fases.
> **Base**: [20260725-c1-ingesta-esquema-real-base.plan.md](.claude/analysis/plans/20260725-c1-ingesta-esquema-real-base.plan.md)
> (✅ en master: parser del esquema real xlsx/CSV con normalización — C2 lo reusa
> como fuente de la carga),
> [20260725-c3-conversaciones-solicitudes-postgres.plan.md](.claude/analysis/plans/20260725-c3-conversaciones-solicitudes-postgres.plan.md)
> (✅ en master: patrón SQLModel `db.get_engine()` + fallback SQLite + tests con
> engine inyectado — C2 copia ese patrón tal cual) y
> [20260725-b3-propension-multicategoria-explicable.plan.md](.claude/analysis/plans/20260725-b3-propension-multicategoria-explicable.plan.md)
> (✅ en master: el motor puntúa `has_children/has_vehicle/has_credit` — las
> columnas sintéticas de C2 alimentan exactamente esas señales).
> Tarea del vault: `07 - Tareas/Feature C - Datos y persistencia/C2 - Base de afiliados en Postgres.md`
> (depende de **C1 ✅**; **bloquea G3 y H4**; capa back; estimación 3h).
> Decisiones que la gobiernan: DEC-005 (base real en el motor) y decisión de
> equipo 2026-07-24 (complemento sintético claramente marcado).
> **Proyectos afectados**: backend.
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

La base de afiliados vive en una tabla **`afiliados`** de Postgres (Dokploy; SQLite
local como fallback dev, igual que C3), indexada por `SERIE`, cargada por un script
batch que reusa el parser de C1. Donde la data real no aporta señal (4 de las 5
marcas de consumo vienen casi vacías — hallazgo crítico del vault), se complementa
con **columnas sintéticas `sint_*`** deterministas y claramente separadas de las
reales. `perfilar_cliente()` deja de depender del dict en memoria: consulta la tabla
por SERIE (con cache), y el perfil de un afiliado real llega al motor B3 **con
señales** — el bot no pregunta lo que la base ya sabe.

Criterios de aceptación del vault:
1. `SELECT count(*)` ≈ 500k tras la carga; lookup por SERIE < 50 ms.
2. El bot reconoce una SERIE real y arma el perfil sin preguntar lo que la base sabe.
3. Columnas sintéticas distinguibles de las reales (naming `sint_`) y documentadas
   en el README del backend.

## Contexto / hallazgos del análisis

**C1 dejó la ingesta lista y probada:**
[affiliates.py](backend/app/repositories/affiliates.py) parsea el esquema real
(xlsx/CSV `;`, `HEADER_MAP` en
[affiliates.py:44-60](backend/app/repositories/affiliates.py#L44-L60),
normalización por dígitos, `load_errors`). La carga a Postgres NO re-implementa
nada de eso: el script consume `_parse_csv`/`load_from_csv` y vuelca perfiles.

**C3 dejó el patrón de persistencia exacto a copiar:**
- Engine singleton perezoso con fallback SQLite
  ([db.py:47-60](backend/app/repositories/db.py#L47-L60)); URLs `postgresql://` se
  reescriben a `postgresql+psycopg://`
  ([db.py:32-36](backend/app/repositories/db.py#L32-L36)). `DATABASE_URL` ya existe
  en [config.py:16](backend/app/core/config.py#L16) y
  [.env.example:27](backend/.env.example#L27) — **cero env vars nuevas**.
- Modelo tabla = SQLModel `table=True` sin `from __future__ import annotations`
  ([conversation.py:1-13](backend/app/models/conversation.py#L1-L13));
  `init_db` importa los modelos y hace `create_all`
  ([db.py:63-71](backend/app/repositories/db.py#L63-L71)) — C2 solo agrega su
  import ahí.
- Repos resuelven engine perezosamente por operación y aceptan engine inyectado
  para tests SQLite in-memory con `StaticPool`
  ([conversations.py:33-37](backend/app/repositories/conversations.py#L33-L37),
  [test_conversation_repository.py:20-28](backend/tests/test_conversation_repository.py#L20-L28)).

**Radio de impacto — quién consume el lookup hoy:**
`AffiliateRepository.find_by_document` ([affiliates.py:143-144](backend/app/repositories/affiliates.py#L143-L144))
← [AffiliateService.lookup/resolve](backend/app/services/affiliate.py#L17-L52)
← [`_perfilar_cliente`](backend/app/services/agent_tools.py#L134-L151) (tool del
LLM) y [ConversationService.create](backend/app/services/conversation.py#L54-L62)
(flujo REST). La regla "cada service es dueño de UN repository" se respeta
haciendo el cambio DENTRO de `AffiliateRepository` (modo DB con fallback CSV), sin
tocar la firma pública `find_by_document/exists/count` — el service no cambia en
F1.

**El hueco que hace necesaria la parte sintética (y su cableado):**
el motor B3 ([propensity.py](backend/app/services/propensity.py)) puntúa
Movilidad/Crédito/Vida con `has_vehicle/has_credit/has_children` vía `getattr` —
pero `AffiliateProfile` ([affiliate.py](backend/app/models/affiliate.py)) no tiene
esos campos, y `_perfilar_cliente` los copia **solo de lo declarado**
([agent_tools.py](backend/app/services/agent_tools.py)). Hoy un afiliado real por
SERIE llega al motor sin ninguna señal de esas categorías (la base real no trae
vehículo/crédito/hijos). Sin la fase de integración (F3), las columnas sintéticas
serían letra muerta: se generarían pero jamás llegarían al motor.

**Marcas reales casi vacías (vault):** solo DROGUERIA tiene señal (17,6%);
HOTELES/AGENCIAS/VIVIENDA/PISCILAGO < 0,05%. Además la anomalía droguería >45 años
sigue sin respuesta de mentores → **ninguna regla nueva depende de droguería en
esos rangos** (C2 no toca reglas del motor; solo transporta datos).

**Ámbito de escritura de los agentes** (backend: `app|tests|.env.example`): el
script de carga va en **`backend/app/scripts/cargar_afiliados.py`** (dentro de
`app/`, ejecutable con `python -m app.scripts.cargar_afiliados`) — no en un
`scripts/` raíz fuera del ámbito. La doc de columnas sintéticas del criterio 3 va
en [backend/README.md](backend/README.md); si el ámbito del implementer lo
bloquea, la escribe el orquestador/usuario en el checkpoint de F3 (contenido
dictado por el plan).

## Decisiones pendientes (bloqueantes)

(ninguna — las dos decisiones de diseño quedan fijadas aquí:
**(a) generación sintética determinista por SERIE** — hash estable (p. ej.
`sha256(f"{serie}:{campo}")` → entero) decide cada valor, así la carga es
reproducible, testeable y defendible ante el jurado ("misma SERIE, mismo perfil
sintético siempre"); nada de `random` global.
**(b) distribuciones verosímiles iniciales**, calibrables sin tocar código de
consulta: `sint_tiene_vehiculo` ≈ 28%, `sint_tiene_credito` ≈ 35%,
`sint_tiene_hijos` correlacionada con el segmento familiar real (RHO/LAMBDA ≈ 65%,
resto ≈ 25% — usa la única señal real disponible), `sint_tipo_vivienda` ≈ 40%
apartment / 25% house / 35% NULL. Los tests fijan determinismo y rangos amplios,
no porcentajes exactos.)

## Principios

- **Patrón C3, cero invención**: mismo `db.get_engine()`, mismo fallback SQLite,
  engine inyectable en tests, `create_all` sin Alembic.
- **Real y sintético nunca se mezclan**: en la tabla, lo sintético SIEMPRE con
  prefijo `sint_`; en el modelo de dominio los campos se llenan desde `sint_*` con
  el origen documentado. El script jamás "inventa" en columnas reales.
- **Firmas públicas intactas** en F1-F2 (`find_by_document/exists/count`); el
  cableado del perfil (F3) es aditivo (defaults `None`).
- **Fallback dev sin fricción**: sin `DATABASE_URL` y sin tabla cargada, todo
  sigue funcionando con el CSV/xlsx de C1 (nadie del equipo se bloquea).
- Verde por fase (`.venv\Scripts\python.exe -m pytest -q`), cero dependencias
  nuevas, cero env vars nuevas, la data real nunca entra al repo.

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | backend | Ninguno | 5m | _(sin commit)_ |
| 1 | Tabla `afiliados` + lookup por SERIE con fallback CSV y cache | backend | Medio (fuente del lookup) | 40m | `feat(back): serve affiliate lookups from postgres table` |
| 2 | Generador sintético determinista + script de carga batch | backend | Aditivo | 40m | `feat(back): load affiliates with deterministic synthetic columns` |
| 3 | Perfil de afiliado real con señales al motor + doc `sint_*` | backend | Medio (funnel) | 35m | `feat(back): profile real affiliates with base and synthetic signals` |

Total: ~120m (dentro de las 3h). G3 (proactivo: queries reales sobre `afiliados`)
y H4 (guion multicategoría con SERIE real) quedan desbloqueadas.

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: backend
**Objetivo**: punto de partida verde e insumos confirmados.
**Archivos afectados**: ninguno.
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` → línea base.
2. Confirmar que la muestra real existe localmente (read-only):
   `...\colsubsidio-brain\01 - Reto Seguros\datos\Usos_Productos_Afiliados_SIN_ID.xlsx`.
3. Registrar si hay `DATABASE_URL` local (Docker de
   [20260724-postgres-local-docker.plan.md](.claude/analysis/plans/20260724-postgres-local-docker.plan.md))
   o si el smoke de carga usará SQLite/Postgres remoto — solo informativo.
4. `npm run build` opcional (frontend no se toca).

**Pruebas / verificación**: las de arriba.
**Riesgos**: ninguno.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit)_

---

## Fase 1 — Tabla `afiliados` + lookup por SERIE con fallback CSV y cache

**Proyecto**: backend
**Objetivo**: existe la tabla y el repositorio consulta la BD primero; sin BD
cargada, el comportamiento actual (CSV/xlsx en memoria) sigue intacto. El service y
sus callers NO cambian.
**Archivos afectados**:
- `backend/app/models/affiliate_record.py` (nuevo) — `AffiliateRecord(SQLModel,
  table=True)`, `__tablename__ = "afiliados"`: `serie: str` PK (el índice por SERIE
  del criterio 1 es el PK), columnas reales espejo de
  [AffiliateProfile](backend/app/models/affiliate.py) (`gender, age_range,
  salary_range, category, household_segment, population_segment, pyramid,
  empresa_foco, city, uses_*` — todas nullable salvo `serie` y `age_range`), y las
  sintéticas **`sint_tiene_vehiculo: bool | None`, `sint_tiene_credito: bool |
  None`, `sint_tiene_hijos: bool | None`, `sint_tipo_vivienda: str | None`** +
  `loaded_at: datetime`. Estilo de
  [conversation.py](backend/app/models/conversation.py) (sin `from __future__`).
- [db.py](backend/app/repositories/db.py) — `init_db` importa también
  `affiliate_record` (una línea en
  [db.py:69](backend/app/repositories/db.py#L69)).
- [affiliates.py](backend/app/repositories/affiliates.py) — `AffiliateRepository`
  gana modo BD manteniendo firmas: `__init__(csv_path=None, engine=None)` (engine
  inyectable, resolución perezosa como
  [conversations.py:33-37](backend/app/repositories/conversations.py#L33-L37));
  `find_by_document` → 1) cache dict en memoria, 2) `SELECT` por PK en la tabla —
  si devuelve fila, mapear a `AffiliateProfile` y cachear, 3) si la tabla no
  existe/está vacía/falla la conexión → camino CSV actual (loggeando una vez el
  fallback). `exists/count` siguen la misma cascada. Mapeo fila→perfil en un solo
  lugar (`_record_to_profile`).
- Tests (`tests/test_affiliates_db.py`, nuevo — patrón de
  [test_conversation_repository.py:20-28](backend/tests/test_conversation_repository.py#L20-L28)
  con SQLite in-memory + `StaticPool`): fila insertada → `find_by_document` la
  devuelve con todos los campos mapeados (reales y `sint_*` → ver F3 para señales;
  aquí basta el mapeo crudo); SERIE inexistente → `None`; segunda llamada sale del
  cache (p. ej. borrar la fila y verificar que el cache aún responde); tabla vacía
  → fallback al CSV fixture de C1 (comportamiento actual intacto); BD rota (engine
  a ruta inválida) → no explota, cae a CSV.

**Impacto en contrato API (front↔back)**: No — capa de datos interna; ninguna
ruta/shape/env var visible cambia.
**Acciones**:
1. TDD-light: tests nuevos primero (rojos: no existe `AffiliateRecord` ni modo BD).
2. Modelo + registro en `init_db` + modo BD con cascada y cache en el repo.
3. Suite completa verde (los tests CSV de C1 en
   [test_affiliates.py](backend/tests/test_affiliates.py) NO se editan — fijan el
   fallback).

**Pruebas / verificación**: pytest completo verde; negativo: BD inaccesible → el
lookup no lanza, usa CSV (test explícito).
**Riesgos**: engine global SQLite creándose en tests por accidente → mitigado con
resolución perezosa + engine inyectado (lección ya aprendida en C3, ver docstring
[conversations.py:14-17](backend/app/repositories/conversations.py#L14-L17)).

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `feat(back): serve affiliate lookups from postgres table`

---

## Fase 2 — Generador sintético determinista + script de carga batch

**Proyecto**: backend
**Objetivo**: cargar la base real a la tabla en minutos, generando las columnas
`sint_*` de forma determinista y separada de lo real (criterios 1 y 3-naming).
**Archivos afectados**:
- `backend/app/services/synthetic.py` (nuevo, service puro sin repo) —
  `synthetic_for(profile: AffiliateProfile) -> dict`: hash estable
  (`sha256(f"{serie}:{campo}")` → entero → umbral) decide `sint_tiene_vehiculo`
  (≈28%), `sint_tiene_credito` (≈35%), `sint_tiene_hijos` (RHO/LAMBDA ≈65% /
  resto ≈25%, usando `household_segment` real), `sint_tipo_vivienda`
  (≈40% "apartment" / ≈25% "house" / ≈35% `None`). Sin `random`, sin estado.
- `backend/app/scripts/__init__.py` + `backend/app/scripts/cargar_afiliados.py`
  (nuevos; DENTRO de `app/` por el ámbito de agentes) — CLI
  `python -m app.scripts.cargar_afiliados <ruta.xlsx|csv> [--replace]`:
  1) parsea con el `AffiliateRepository` de C1 (`load_from_csv` — reusa xlsx/CSV,
  normalización y `load_errors`), 2) genera `sint_*` por perfil, 3) inserta por
  lotes (~5.000 filas por `INSERT` multi-values vía SQLAlchemy Core sobre
  `db.get_engine()` — funciona igual en Postgres y SQLite; `--replace` = `DELETE`
  previo), 4) imprime resumen: total cargado, errores de parseo, duración, y
  recuerda que la fuente NUNCA se commitea.
- Tests (`tests/test_synthetic.py` + ampliar `tests/test_affiliates_db.py`):
  determinismo (misma SERIE → mismos `sint_*` en llamadas y procesos distintos —
  valores fijos esperados para 2-3 SERIEs literales); distribución en rango amplio
  (sobre 400 SERIEs sintéticas, `sint_tiene_vehiculo` entre 15% y 45%, hijos
  RHO > hijos resto); correlación con segmento; carga end-to-end con engine SQLite
  in-memory: fixture CSV de ~10 filas → script (función `main`/`load_to_db`
  importable) → `count()` correcto, re-ejecución con `--replace` no duplica
  (idempotencia), fila corrupta reportada sin abortar.

**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. TDD-light: tests de determinismo/distribución y de carga primero.
2. Implementar `synthetic.py` y el script batch.
3. Suite completa verde.
4. **Smoke criterio 1 (manual, local, fuera de CI)**: con `DATABASE_URL` apuntando
   al Postgres local (Docker) o de Dokploy:
   `python -m app.scripts.cargar_afiliados "...\Usos_Productos_Afiliados_SIN_ID.xlsx" --replace`
   → registrar en el checkpoint: `count(*)` (~500k), duración de carga, y tiempo de
   `find_by_document` para 3 SERIEs (< 50 ms, trivial con PK). ⚠️ En `/launch-plan`
   este smoke se OMITE (requiere `.env`/BD viva) y queda como pendiente manual.

**Pruebas / verificación**: pytest completo verde; negativo: ruta de archivo
inexistente → el script termina con mensaje claro y exit code ≠ 0, sin traceback
crudo.
**Riesgos**: memoria al cargar 500k (perfiles + dicts) → se procesa en streaming
por lotes (parsear todo con C1 ya está probado; el volcado va por chunks);
duplicados de SERIE en la fuente → el dict de C1 ya deduplica (última gana),
documentarlo en el resumen del script.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 3 sin aprobación del usuario.
**Commit sugerido**: `feat(back): load affiliates with deterministic synthetic columns`

---

## Fase 3 — Perfil de afiliado real con señales al motor + doc `sint_*`

**Proyecto**: backend
**Objetivo**: que la tabla sirva de algo en la conversación (criterio 2): una SERIE
real produce un perfil CON señales (reales + sintéticas) que llegan al motor B3, y
lo declarado en conversación siempre pisa lo sintético.
**Archivos afectados**:
- [affiliate.py (model)](backend/app/models/affiliate.py) — `AffiliateProfile` gana
  `has_children: bool | None`, `has_vehicle: bool | None`, `has_credit: bool | None`
  (defaults `None`, aditivo). El docstring documenta el origen: en perfiles desde
  BD estos campos vienen de `sint_*` (y `property_type` de `sint_tipo_vivienda`);
  en perfiles declarados, de la conversación.
- [affiliates.py](backend/app/repositories/affiliates.py) — `_record_to_profile`
  (F1) mapea `sint_tiene_hijos→has_children`, `sint_tiene_vehiculo→has_vehicle`,
  `sint_tiene_credito→has_credit`, `sint_tipo_vivienda→property_type` (solo modo
  BD: el camino CSV no tiene sintéticos y queda en `None` — real y sintético
  siguen distinguibles por construcción).
- [agent_tools.py](backend/app/services/agent_tools.py) — `_perfilar_cliente`:
  el `ProfileData` final fusiona base + declarado con **declarado gana**:
  `has_vehicle=declared.has_vehicle if declared.has_vehicle is not None else
  resolved.has_vehicle` (ídem hijos/crédito/`has_family`←`has_children` no:
  `has_family` sigue solo declarado). `property_type/zone/stratum/age_range` ya
  vienen de `resolved` (sin cambio).
- [conversation.py](backend/app/services/conversation.py) — `create`: el
  `ProfileData` desde afiliado incluye también `has_children/has_vehicle/
  has_credit` del perfil resuelto (paridad REST/tool).
- [backend/README.md](backend/README.md) — sección "Base de afiliados y columnas
  sintéticas" (criterio 3): esquema de la tabla, qué columnas son reales vs
  `sint_*`, cómo se generan (determinismo por SERIE, distribuciones), cómo correr
  el script, y la regla "la data real nunca entra al repo". (Si el ámbito del
  implementer no permite README, lo escribe el orquestador/usuario en este
  checkpoint con el contenido anterior.)
- Tests (ampliar `tests/test_affiliates_db.py` y `tests/test_agent_tools.py`):
  fila con `sint_tiene_vehiculo=True` → `perfilar_cliente` con esa SERIE deja
  `ctx.profile.has_vehicle is True` y `recomendar_seguro` devuelve
  `movilidad-auto` **sin declarar nada** (criterio 2 end-to-end sin LLM);
  declarado pisa sintético (`args has_vehicle=False` + base `True` → `False`);
  SERIE no encontrada → flujo declarado intacto (tests existentes lo cubren, no se
  editan).

**Impacto en contrato API (front↔back)**: Sí — **sin cambio de shape**: `ProfileData`
ya tenía estos campos desde B3; lo que cambia son los **valores** (un afiliado por
SERIE puede llegar con `has_vehicle: true` de fábrica y la recomendación variar
sin preguntas). El frontend no requiere cambios (tarjetas D3 ya son dinámicas);
el guion del demo (H4) gana el caso "entro con mi cédula/SERIE y me reconoce".
**Acciones**:
1. TDD-light: tests de fusión y del flujo SERIE→movilidad primero.
2. Modelo + mapeo + fusión en tool y REST.
3. README (criterio 3).
4. Suite completa verde.

**Pruebas / verificación**: pytest completo verde; smoke manual opcional con BD
cargada: `POST /api/v1/conversations` con `document_number` de una SERIE real →
`profile` armado sin preguntas. Negativo: BD vacía → todo el funnel actual sigue
verde (fallback CSV, tests existentes sin editar).
**Riesgos**: doble fuente de verdad declarado/sintético → regla única "declarado
gana" centralizada en `_perfilar_cliente` y testeada; sobre-venta del dato
sintético en el pitch → mitigada por el naming `sint_` + README (defensa explícita
ante el jurado, decisión de equipo 2026-07-24).

🛑 **CHECKPOINT** — fin del plan.
**Commit sugerido**: `feat(back): profile real affiliates with base and synthetic signals`

---

## Deuda / fuera de alcance (anotada para el vault)

- **G3 (proactivo)**: queries agregadas sobre `afiliados` ("N afiliados con perfil
  X") — la tabla ya queda lista; el endpoint/panel es de G3.
- **Cache con TTL/invalidez**: el cache de lookup es un dict simple por proceso
  (suficiente para el demo); si la tabla se recarga en caliente, reiniciar el
  backend.
- **Marcas de consumo como señal del motor**: sigue bloqueado por S6/S7 (droguería
  >45 sin respuesta de mentores) — C2 las persiste, no las puntúa.
- **Base completa de 1,5M (CSV `;`)**: mismo script, misma ruta — solo cambia el
  archivo de entrada; el batch por lotes ya lo soporta.
- **A4 (perfil enriquecido persistente por conversación)**: complementario — C2
  cubre el perfil BASE (real+sintético); lo declarado sigue viviendo en la sesión
  hasta A4.
