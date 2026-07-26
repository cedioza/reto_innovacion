# Plan — C1: Ingesta con el esquema real de la base · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-25 · **Tipo**: plan de implementación por fases.
> **Base**: (ninguno directo sobre ingesta; se cita
> [20260725-b3-propension-multicategoria-explicable.plan.md](.claude/analysis/plans/20260725-b3-propension-multicategoria-explicable.plan.md)
> porque su motor usa `household_segment` del perfil base — C1 garantiza que ese
> campo por fin cargue con datos reales).
> Tarea del vault: `07 - Tareas/Feature C - Datos y persistencia/C1 - Ingesta con el esquema real de la base.md`
> (sin dependencias; **bloquea C2** — base en Postgres; capa back; estimación 3h).
> Decisión que la gobierna: `DEC-005 — Base real de afiliados en el motor de
> propensión` · deuda aceptada D8 (normalización mínima).
> **Proyectos afectados**: backend.
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

`AffiliateRepository` carga el archivo REAL de Colsubsidio. El cargador actual fue
escrito con columnas adivinadas que **no existen en la base real** (`RANGO_SALARIO`,
`SEGMENTO_HOGAR` interpretado como estrato numérico, `SEÑAL_CONSUMO_1..5`) — hoy no
cargaría un solo registro del archivo oficial. C1 lo reescribe contra el esquema
real (`SERIE, GENERO, RANGO_EDAD, RANGO_SALARIAL, CATEGORIA,
SEGMENTO_GRUPO_FAMILIAR, SEGMENTO_POBLACIONAL, PIRAMIDE_NUEVA, EMPRESA_FOCO,
CIUDAD_AFILIADO` + marcas `HOTELES, PISCILAGO, DROGUERIA, AGENCIAS, VIVIENDA`),
soportando xlsx (muestra de 500k) y CSV `;` (base completa de 1,5M), con
normalización mínima (deuda D8) y filas corruptas reportadas sin tumbar la carga.

Criterios de aceptación del vault:
1. La muestra real de 500k carga completa y `find_by_document(SERIE)` responde
   (smoke con el archivo real local).
2. Test con fixture CSV `;` de 20 filas del esquema real: perfiles correctos, filas
   corruptas reportadas sin tumbar la carga.
3. Los dos esquemas de rango salarial quedan normalizados a uno solo.

## Contexto / hallazgos del análisis

**El cargador actual no puede leer la base real:**
[affiliates.py:8-9](backend/app/repositories/affiliates.py#L8-L9) documenta el
esquema adivinado (`RANGO_SALARIO;SEGMENTO_HOGAR;SEGMENTO_POBLACION;CIUDAD;
SEÑAL_CONSUMO_1..5`) y [_row_to_profile](backend/app/repositories/affiliates.py#L98-L124)
mapea `SEGMENTO_HOGAR` → `stratum` como entero — en la base real
`SEGMENTO_GRUPO_FAMILIAR` trae códigos griegos (LAMBDA, RHO…), así que con el
archivo real ese campo caería siempre al default y **ninguna columna coincidiría**.
El fixture de [test_affiliates.py:11-15](backend/tests/test_affiliates.py#L11-L15)
consagra el esquema inventado → se reescribe (edición deliberada: el test describía
un formato que nunca existió).

**Radio de impacto contenido — las firmas públicas no cambian:**
`find_by_document / exists / count / load_from_csv` se conservan; los únicos
consumidores son [AffiliateService](backend/app/services/affiliate.py#L15-L19)
(composición, no toca columnas) y de ahí
[agent_tools.py:134-151](backend/app/services/agent_tools.py#L134-L151) y
[conversation.py:54-62](backend/app/services/conversation.py#L54-L62), que leen
`age_range/stratum/property_type/zone` — todos campos que se mantienen.
[propensity.py](backend/app/services/propensity.py#L13) acepta `AffiliateProfile`
por `getattr`, y el plan B3 usará `household_segment` — C1 hace que ese campo cargue
con los códigos reales.

**Campos del modelo vs. esquema real:**
[AffiliateProfile](backend/app/models/affiliate.py) ya tiene `household_segment`,
`population_segment`, `salary_range`, pero le faltan **género, categoría, pirámide,
empresa foco y las 5 marcas de consumo** que sí trae la base (y que G3/proactivo y
la calibración de B3 quieren). Se agregan como opcionales — aditivo. La base real
**no trae estrato ni tipo de propiedad**: `stratum` conserva su default 3 y
`property_type=None` (se declara en conversación) — comportamiento actual,
documentado.

**Trampas del archivo real (vault `Análisis base de afiliados`):**
- **Dos esquemas de rango salarial mezclados** (~140 filas con buckets viejos tipo
  "Entre 2 y 4 SMLV") → normalizar al cargar (criterio 3).
- **Mojibake** en el xlsx ("a�os"): el texto ya viene corrupto en la fuente — la
  normalización no puede confiar en las letras; sí en los **dígitos**.
- **RANGO_SALARIAL con 4.988 nulos** (los mismos de `SEGMENTO_POBLACIONAL=OMEGA`)
  → `salary_range=None`, nunca fila descartada.
- **`CIUDAD_AFILIADO` 58% nulo** → el mapeo `zone="urban" si hay ciudad` actual
  ([affiliates.py:113-118](backend/app/repositories/affiliates.py#L113-L118))
  clasificaría 58% como rural; se cambia a `zone=None` cuando no hay ciudad (el dato
  se pregunta en conversación — Fricción Cero).
- Valores griegos (SIGMA, LAMBDA…): **se guardan como códigos, sin interpretar**
  (regla del vault).
- Marcas `SI/NO` → booleanos (`None` si viene vacío).

**Formato dual xlsx/CSV:** la muestra oficial es
`Usos_Productos_Afiliados_SIN_ID.xlsx` (30 MB, copia local en el vault
`01 - Reto Seguros/datos/`, **excluida de git**); la base completa anunciada es CSV
`;` de ~1,5M. Leer xlsx exige **openpyxl** — dependencia nueva justificada (es el
formato del insumo oficial del reto; DEC-005 exige tolerancia xlsx/CSV). Es la única
dependencia que agrega este plan.

**Higiene detectada de paso (se corrige en Fase 1):**
- El default del código es `backend/data/afiliados.csv`
  ([affiliates.py:23-25](backend/app/repositories/affiliates.py#L23-L25)) pero
  [.env.example:66-68](backend/.env.example#L66-L68) documenta
  `backend/app/data/afiliados.csv` — se unifica en `app/data/` (donde ya viven
  `catalogo/` y `local.db`).
- 🔒 [.gitignore](.gitignore) **no excluye los archivos de datos de afiliados** —
  la regla del vault es "la data NUNCA entra al repo"; se agregan patrones
  explícitos (`backend/app/data/afiliados.*`, `backend/app/data/*.xlsx`).
- `_load()` descarta silenciosamente la lista de errores
  ([affiliates.py:67-71](backend/app/repositories/affiliates.py#L67-L71)) — el
  criterio 2 exige reportarlos.
- 500k perfiles en memoria: `AffiliateProfile` pasa a `@dataclass(slots=True)`
  (una línea, reduce ~2-3× la RAM del dict de instancias; C2 lo llevará a Postgres).

## Decisiones pendientes (bloqueantes)

(ninguna — las tres decisiones de diseño quedan resueltas en este plan:
**openpyxl** entra como única dependencia nueva porque el insumo oficial es xlsx;
el **rango salarial se canonicaliza por dígitos** a `"<min>-<max> SMLV"` /
`"<n>+ SMLV"` — robusto al mojibake y unifica ambos esquemas sin adivinar
etiquetas; los **valores griegos se guardan tal cual**. Si al inspeccionar el
archivo real en la Fase 2 apareciera una columna con nombre distinto al anunciado,
se ajusta el mapa de encabezados — para eso la normalización de headers es data.)

## Principios

- **Verde por fase**: `.venv\Scripts\python.exe -m pytest -q` desde `backend/`.
- **La data real nunca entra al repo**: tests solo con fixture sintética inline; el
  archivo real se usa únicamente en el smoke manual local (criterio 1).
- **Firmas públicas intactas**: `find_by_document/exists/count/load_from_csv` no
  cambian — los services y sus callers no se tocan.
- **Normalización mínima y por datos** (deuda D8): mapa de encabezados + parser de
  rangos por dígitos; nada de interpretar códigos griegos ni marcas vacías.
- **Tolerante, nunca frágil**: fila corrupta → se reporta y se sigue; archivo
  ausente → repo vacío (comportamiento actual que los tests ya fijan).
- Una sola dependencia nueva (openpyxl), cero env vars nuevas (`AFFILIATE_CSV_PATH`
  se reutiliza y ahora acepta también `.xlsx`; se documenta en `.env.example`).

## Normalización definida (referencia de implementación)

| Dato | Regla |
|---|---|
| Encabezados | NFKD sin acentos, MAYÚSCULAS, espacios→`_`, BOM fuera; mapa explícito columna real → campo del modelo |
| `RANGO_SALARIAL` | extraer números con regex (soporta `1.5`): 2 números → `"1-1.5 SMLV"`; "más de N"/un número con señal de tope abierto → `"N+ SMLV"`; sin dígitos/vacío → `None`. Unifica esquema viejo ("Entre 2 y 4 SMLV" → `"2-4 SMLV"`) y nuevo en un solo formato canónico |
| `RANGO_EDAD` | misma canonicalización por dígitos → `"20-35"`, `"55+"` (inmune al mojibake "a�os") |
| Marcas (5) | `SI`→`True`, `NO`→`False`, vacío→`None` |
| Griegos (`CATEGORIA`, `SEGMENTO_*`, `PIRAMIDE_NUEVA`) | string tal cual (trim), vacío→`None` |
| `EMPRESA_FOCO` | string tal cual (`EMP_000001/2`; su semántica de flag es supuesto no confirmado — no se interpreta) |
| `CIUDAD_AFILIADO` | trim; vacío→`city=None` y `zone=None` (ya no "rural" por defecto) |
| Encoding | CSV: `utf-8-sig` con fallback `latin-1`; valores con `\ufffd` se conservan (la canonicalización por dígitos los vuelve inocuos) |
| Fila corrupta | sin `SERIE` o campos imposibles → entrada en el reporte de errores (`fila N: motivo`), la carga continúa |

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | backend | Ninguno | 5m | _(sin commit)_ |
| 1 | Parser del esquema real (CSV `;`) + normalización + reporte de errores | backend | Medio (reescritura interna del loader) | 45m | `feat(back): load affiliates with the real dataset schema` |
| 2 | Soporte xlsx (openpyxl) + smoke con la muestra real de 500k | backend | Aditivo | 30m | `feat(back): read the 500k xlsx affiliate sample` |

Total: ~80m (dentro de las 3h de la tarea). C2 (Postgres) queda desbloqueada: la
ingesta ya produce perfiles con el esquema real, listos para volcarse a tabla.

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: backend
**Objetivo**: punto de partida verde y confirmación de insumos locales.
**Archivos afectados**: ninguno.
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` → registrar línea base.
2. Confirmar que la muestra real existe localmente (read-only):
   `C:\machine\development\progress\colsubsidio\colsubsidio-brain\01 - Reto Seguros\datos\Usos_Productos_Afiliados_SIN_ID.xlsx`
   (30 MB) — es el insumo del smoke de la Fase 2. **No se copia al repo.**
3. Verificar que `git check-ignore` aún NO cubre `backend/app/data/afiliados.csv`
   (evidencia del hueco de higiene que cierra la Fase 1).
4. Frontend no se toca (registro opcional de `npm run build`).

**Pruebas / verificación**: las de arriba.
**Riesgos**: ninguno.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit)_

---

## Fase 1 — Parser del esquema real (CSV `;`) + normalización + reporte de errores

**Proyecto**: backend
**Objetivo**: el loader entiende el esquema real con la normalización de la tabla de
arriba y reporta filas corruptas sin tumbar la carga (criterios 2 y 3). Todo con
fixture sintética — la data real no aparece en esta fase.
**Archivos afectados**:
- [affiliate.py (model)](backend/app/models/affiliate.py) — `AffiliateProfile` gana
  opcionales `gender`, `category`, `pyramid`, `empresa_foco`, `salary_range` (ya
  existe), y las 5 marcas `uses_hoteles/uses_piscilago/uses_drogueria/uses_agencias/
  uses_vivienda: bool | None`; pasa a `@dataclass(slots=True)`.
- [affiliates.py (repo)](backend/app/repositories/affiliates.py) — reescritura
  interna: mapa de encabezados normalizados → campo, `_normalize_range()` (dígitos →
  canónico, compartida por salario y edad), marcas SI/NO, `zone=None` sin ciudad,
  reporte de errores accesible (p. ej. propiedad `load_errors: list[str]` poblada en
  `_parse_csv`, hoy descartada en
  [affiliates.py:67-71](backend/app/repositories/affiliates.py#L67-L71)) +
  `logger.warning` con el conteo al terminar una carga con errores. Docstring del
  módulo actualizado al esquema real. `DEFAULT_AFFILIATE_CSV_PATH` →
  `app/data/afiliados.csv` (consistente con [.env.example:66-68](backend/.env.example#L66-L68)).
- [test_affiliates.py](backend/tests/test_affiliates.py) — fixture reescrita al
  **esquema real** (~20 filas sintéticas, criterio 2): encabezados reales con BOM,
  filas con esquema salarial nuevo Y viejo (ambas → canónico, criterio 3), mojibake
  simulado ("36-45 a\ufffdos"), marcas SI/NO/vacío, `RANGO_SALARIAL` vacío,
  `CIUDAD_AFILIADO` vacío → `zone is None`, 2 filas corruptas (sin SERIE) →
  cargan N−2 y `load_errors` las reporta con número de fila. Los tests de service
  ([test_affiliates.py:65-91](backend/tests/test_affiliates.py#L65-L91)) quedan
  intactos.
- [.gitignore](.gitignore) — `backend/app/data/afiliados.*` y
  `backend/app/data/*.xlsx` (regla 🔒 del vault).
- [.env.example](backend/.env.example) — comentario de `AFFILIATE_CSV_PATH`
  actualizado: acepta `.csv` (`;`) o `.xlsx`, default `app/data/afiliados.csv`.

**Impacto en contrato API (front↔back)**: No — nada de esto viaja al frontend
(`AffiliateProfile` nunca se expone; `ProfileData` no cambia).
**Acciones**:
1. TDD-light: reescribir la fixture y los tests primero (rojos: el loader actual no
   entiende el esquema real).
2. Ampliar el modelo (aditivo) y reescribir `_row_to_profile`/`_parse_csv` con la
   tabla de normalización.
3. `.gitignore` + `.env.example` + default de ruta.
4. Suite completa verde.

**Pruebas / verificación**: pytest completo verde; en particular los tests de
service/tools/propensity NO editados (las firmas y campos consumidos no cambian).
Negativo: archivo inexistente → repo vacío sin excepción (test existente
[test_affiliates.py:50-53](backend/tests/test_affiliates.py#L50-L53) sigue verde).
**Riesgos**: cambiar `zone` de "rural" a `None` sin ciudad — verificado: ningún
caller depende de ese valor sintético (propensity trata `None` como "sin señal");
si un test lo fijara, se ajusta el fixture, no la regla.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `feat(back): load affiliates with the real dataset schema`

---

## Fase 2 — Soporte xlsx (openpyxl) + smoke con la muestra real de 500k

**Proyecto**: backend
**Objetivo**: el mismo repositorio lee la muestra oficial xlsx (criterio 1); la base
completa CSV `;` de 1,5M usará el camino ya probado en Fase 1.
**Archivos afectados**:
- [pyproject.toml](backend/pyproject.toml) — `openpyxl>=3.1` en `dependencies`
  (única dependencia nueva del plan; justificación: el insumo oficial es xlsx).
  ⚠️ Instalación (`.venv\Scripts\pip install -e .[dev]`) la corre el usuario u
  orquestador en el checkpoint — los agentes de `/run-plan` tienen prohibido
  instalar.
- [affiliates.py](backend/app/repositories/affiliates.py) — `_parse_csv` se
  generaliza: si la ruta termina en `.xlsx`, iterar con
  `openpyxl.load_workbook(path, read_only=True, data_only=True)` produciendo los
  mismos dicts fila→valor que `csv.DictReader` (la normalización de Fase 1 se
  reutiliza tal cual — un solo camino de mapeo). Import de openpyxl local a la rama
  xlsx (si falta el paquete y nadie usa xlsx, nada se rompe).
- Tests (ampliar `test_affiliates.py`): fixture xlsx mínima generada **en el test**
  con openpyxl (3-4 filas, mismo esquema real) → mismos perfiles que su CSV
  equivalente; ruta `.xlsx` inexistente → repo vacío sin excepción.

**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Agregar dependencia + instalar (usuario/orquestador).
2. TDD-light: test xlsx primero (rojo: hoy cualquier ruta se lee como CSV).
3. Implementar la rama xlsx reutilizando la normalización.
4. Suite completa verde.
5. **Smoke criterio 1 (manual, local, read-only sobre la data real)**: desde
   `backend/` con el venv, script efímero o consola:
   `AffiliateRepository(csv_path=r"...\datos\Usos_Productos_Afiliados_SIN_ID.xlsx")`
   → `count() == 500_000` (±, según filas corruptas reportadas en `load_errors`),
   `find_by_document(<SERIE tomada del propio archivo>)` devuelve perfil con
   `salary_range` canónico y segmentos griegos como códigos; registrar en el
   checkpoint: total cargado, nº de errores y tiempo de carga. **El archivo y
   cualquier salida con SERIEs reales no se commitean.**

**Pruebas / verificación**: pytest completo verde + smoke manual documentado en el
checkpoint. Negativo: xlsx corrupto/ilegible → repo vacío + error reportado, nunca
excepción al caller.
**Riesgos**: tiempo/memoria de 500k filas xlsx (~30 MB): `read_only=True` la
transmite por streaming y `slots=True` (Fase 1) contiene la RAM; si la carga
resultara lenta para el arranque del dev server, queda anotado que C2 (Postgres) es
la solución definitiva — no se optimiza más aquí. Si el archivo real trae un
encabezado distinto al anunciado, se ajusta el mapa de headers (es data) y se
re-corre el smoke.

🛑 **CHECKPOINT** — fin del plan.
**Commit sugerido**: `feat(back): read the 500k xlsx affiliate sample`

---

## Deuda / fuera de alcance (anotada para el vault)

- **C2**: volcar los perfiles cargados a Postgres (tabla afiliados) y consultar por
  ahí; C1 deja el formato de perfil definitivo para esa tabla.
- **Mapeo de `RANGO_EDAD` real (20-35, 36-45…) a los buckets que usan los motores**
  (`18-25`, `26-40`, `41-55`, `65+` en propensity/quote): hoy un afiliado real con
  "36-45" no dispara las reglas de edad pensadas para los rangos declarados. Es
  decisión de calibración de B3/B5 (¿qué bucket canónico gana?), no de ingesta — la
  canonicalización por dígitos de C1 deja los valores listos para mapear.
- **Marcas de consumo como señal de propensión**: bloqueado por S6/S7 (marcas casi
  vacías + anomalía droguería >45) hasta respuesta de mentores; C1 solo las carga.
- **`EMPRESA_FOCO` y `CATEGORIA` griega**: semántica sin confirmar (supuestos del
  vault) — se almacenan sin interpretar.
- **Ingesta de la base completa (1,5M, CSV `;`)**: el camino queda probado con
  fixture; cuando llegue el archivo, es cambiar `AFFILIATE_CSV_PATH`.
