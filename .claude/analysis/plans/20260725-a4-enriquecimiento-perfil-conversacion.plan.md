# Plan — A4: Enriquecimiento de perfil en conversación · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-25 · **Tipo**: plan de implementación por fases.
> **Base**: [20260725-b3-propension-multicategoria-explicable.plan.md](.claude/analysis/plans/20260725-b3-propension-multicategoria-explicable.plan.md)
> (✅ `ProfileData` ya transporta `has_children/has_vehicle/has_credit` y el motor
> re-rankea con ellas — A4 amplía QUÉ se captura y lo hace persistente),
> [20260725-c3-conversaciones-solicitudes-postgres.plan.md](.claude/analysis/plans/20260725-c3-conversaciones-solicitudes-postgres.plan.md)
> (✅ patrón SQLModel/engine/tests que A4 copia para su tabla) y
> [20260725-c2-base-afiliados-postgres.plan.md](.claude/analysis/plans/20260725-c2-base-afiliados-postgres.plan.md)
> (✅ fusión declarado-gana en `perfilar_cliente` — A4 le suma la capa
> "enriquecido previo por SERIE").
> Tarea del vault: `07 - Tareas/Feature A - Agente conversacional/A4 - Enriquecimiento de perfil en conversacion.md`
> (depende de **A3 ✅** y **C3 ✅**; capa back; estimación 3h). Requisito directo
> del equipo (2026-07-24): "enriquecer el perfil: sí rotundo".
> **Proyectos afectados**: backend.
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

Todo dato nuevo que la persona declare en conversación (hijos —con número—,
mascota, vehículo, crédito, ocupación, hábitos como fumar, tipo de vivienda) se
captura vía una tool **`enriquecer_perfil`**, se **persiste** en una tabla
`perfil_enriquecido` (por sesión y por SERIE), y **alimenta al motor de propensión
en el mismo flujo**. Cuando un cliente identificado vuelve (misma SERIE, otra
sesión u otro canal), su perfil arranca con lo ya aprendido: el argumento
"el sistema aprende de cada conversación" del pitch, con evidencia en BD.

Criterios de aceptación del vault:
1. "Tengo dos hijos y un perro" → quedan `hijos=2`, `mascota=perro` persistidos
   (test).
2. Una recomendación cambia de producto al agregar un dato enriquecido y la razón
   lo cita.
3. Los campos sobreviven un reinicio del backend (están en BD).

## Contexto / hallazgos del análisis

**Lo que YA existe (B3+C2 adelantaron la mitad de A4):**
- `ProfileData` tiene `has_family/has_children/has_vehicle/has_credit`
  ([conversation.py:23-37](backend/app/schemas/conversation.py#L23-L37)) y
  `perfilar_cliente` los captura con fusión declarado-gana
  ([agent_tools.py:133-192](backend/app/services/agent_tools.py#L133-L192)).
- El motor re-rankea con esas señales y sus razones las citan
  ([propensity.py](backend/app/services/propensity.py) — p. ej. `vehicle_declared`).
- El perfil de la sesión ya **sobrevive reinicios**: el orquestador sincroniza
  `ctx.profile → session.profile`
  ([orchestrator.py:174](backend/app/services/orchestrator.py#L174)) y la sesión
  entera se persiste (C3, tabla `conversaciones`).

**Los 3 huecos que A4 cierra:**
1. **No hay captura tipada más allá de booleanos**: "tengo DOS hijos y un perro"
   hoy se reduce a `has_children=true` — el número y la mascota se pierden
   (criterio 1 imposible hoy). Tampoco hay dónde poner ocupación/hábitos (campos
   "Preguntado por la IA" de la Matriz de Perfilamiento).
2. **No hay tabla consultable de lo aprendido**: el perfil vive embebido en el
   JSON de la sesión — G3/panel no pueden consultar "qué sabemos de esta SERIE"
   sin parsear conversaciones. La tarea pide una tabla
   `perfil_enriquecido (session_id/SERIE, campo, valor, timestamp)`.
3. **Lo aprendido muere con la sesión**: si la misma SERIE vuelve mañana (u otro
   canal), `perfilar_cliente` arranca de cero (base + sintético). No hay memoria
   cross-sesión.

**Patrón de persistencia a copiar (C3, cero invención):** modelo SQLModel
`table=True` ([conversation.py (model)](backend/app/models/conversation.py)),
registro en `init_db` ([db.py:63-71](backend/app/repositories/db.py#L63-L71)),
repo con engine inyectable perezoso
([conversations.py:33-37](backend/app/repositories/conversations.py#L33-L37)),
tests con SQLite in-memory + `StaticPool`
([test_conversation_repository.py:20-28](backend/tests/test_conversation_repository.py#L20-L28)).
Cero dependencias nuevas, cero env vars.

**Arquitectura de capas**: la tool NO puede tocar el repo directo — nuevo
`EnrichmentService` (dueño del nuevo repo) compuesto desde los handlers de
[agent_tools.py](backend/app/services/agent_tools.py), igual que
`AffiliateService`/`consent_service`.

**Dónde se citan los datos en razones**: la regla `dependents` de vida
([propensity.py:136-143](backend/app/services/propensity.py#L136-L143)) tiene
`evidence` fija "Hijos declarados: sí" — con `children_count` puede citar
"2 hijos declarados" (criterio 2, refuerzo). El cambio de producto por dato
enriquecido ya está garantizado por B3 (vehículo → movilidad): el test del
criterio 2 usa la TOOL nueva para dispararlo.

**Mascota**: el catálogo NO tiene producto de mascotas (B2 la excluyó por nota
del vault) → `mascota=perro` se captura y persiste (criterio 1) pero no puntúa
ninguna categoría todavía; cuando exista el producto, es 1 regla en
`CATEGORY_RULES`. Anotado en deuda — no se inventa una categoría sin producto.

**Nota de ámbito**: todos los archivos de A4 caen dentro de `app|tests` (ámbito
del implementer). La actualización del `backend/README.md` (documentar la tabla)
la hace el orquestador/usuario en el checkpoint de F3, como en C2.

## Decisiones pendientes (bloqueantes)

(ninguna — decisiones de diseño fijadas en este plan:
**(a) whitelist de campos, no ontología** (nota del vault): `hijos` (entero ≥0),
`mascota` (`perro|gato|otro|ninguna`), `vehiculo` (`si|no`), `credito` (`si|no`),
`fumador` (`si|no`), `ocupacion` (texto corto), `tipo_vivienda`
(`house|apartment`) — los de la Matriz que el flujo actual ya puede aprovechar;
**(b) almacenamiento EAV** (campo/valor string + timestamp), tipado y validado en
el service al leer/escribir; **última escritura gana** por campo;
**(c) prioridad de fusión**: declarado en ESTA conversación > enriquecido previo
(por SERIE) > base real/sintética — coherente con la regla existente de C2.)

## Principios

- Patrón C3 tal cual (modelo + repo + engine inyectable + SQLite in-memory en
  tests); cero dependencias, cero env vars.
- **Capas**: tool → `EnrichmentService` → `EnrichedProfileRepository` → modelo.
  Nada de repos en handlers.
- **Aditivo**: `ProfileData` solo gana `children_count` opcional; ninguna firma
  existente cambia; los tests existentes no se editan.
- **Whitelist cerrada**: campo fuera de la lista → error controlado al LLM
  (`{"error": ...}`), nunca excepción (patrón de `execute_tool`).
- Verde por fase (`.venv\Scripts\python.exe -m pytest -q` desde `backend/`);
  TDD-light con rojo verificado por fase.

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | backend | Ninguno | 5m | _(sin commit)_ |
| 1 | Tabla `perfil_enriquecido` + repo + service | backend | Aditivo | 35m | `feat(back): persist enriched profile fields per session and serie` |
| 2 | Tool `enriquecer_perfil` → perfil → motor (criterios 1 y 2) | backend | Medio (tool nueva + prompt) | 40m | `feat(back): capture enriched profile data in conversation` |
| 3 | Memoria cross-sesión por SERIE + doc | backend | Medio (fusión) | 30m | `feat(back): reuse enriched fields across sessions by serie` |

Total: ~110m (dentro de las 3h de la tarea).

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: backend
**Objetivo**: punto de partida verde.
**Archivos afectados**: ninguno.
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` → línea base
   (registrar conteo — master avanzó con G3/H4).
2. `npm run build` opcional (frontend no se toca).
3. Confirmar en [agent_tools.py](backend/app/services/agent_tools.py) y
   [propensity.py](backend/app/services/propensity.py) que las señales citadas en
   este plan siguen como se describen (G3/H4 no debieron tocarlas).

**Pruebas / verificación**: las de arriba.
**Riesgos**: ninguno.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit)_

---

## Fase 1 — Tabla `perfil_enriquecido` + repo + service

**Proyecto**: backend
**Objetivo**: la persistencia del criterio 3 — campos enriquecidos en BD, por
sesión y por SERIE, consultables y con última-escritura-gana.
**Archivos afectados**:
- `backend/app/models/enriched_field.py` (nuevo) — `EnrichedFieldRecord(SQLModel,
  table=True)`, `__tablename__ = "perfil_enriquecido"`: `id: int PK
  autoincrement`, `session_id: str (index)`, `serie: str | None (index)`,
  `campo: str`, `valor: str`, `created_at: datetime` (UTC). Estilo de
  [conversation.py (model)](backend/app/models/conversation.py).
- [db.py](backend/app/repositories/db.py) — `init_db` importa el modelo nuevo
  (una línea).
- `backend/app/repositories/enriched_profile.py` (nuevo) —
  `EnrichedProfileRepository(engine=None)` con resolución perezosa:
  `add(session_id, serie, campo, valor)`,
  `fields_for_session(session_id) -> dict[str, str]` y
  `fields_for_serie(serie) -> dict[str, str]` (ambos: última escritura gana por
  campo, orden por `created_at`/`id`).
- `backend/app/services/enrichment.py` (nuevo) — `EnrichmentService` (dueño del
  repo): `ALLOWED_FIELDS` con validadores/normalizadores por campo (whitelist de
  la decisión (a): `hijos` int≥0, enums `mascota/vehiculo/credito/fumador`,
  `ocupacion` texto ≤80 chars, `tipo_vivienda` house|apartment);
  `record(session_id, serie, campo, valor) -> valor_normalizado` (ValueError con
  mensaje claro si campo/valor inválido — el handler lo traduce a error
  controlado); `fields_for(session_id, serie=None) -> dict` (sesión primero,
  serie completa lo que falte).
- Tests (`tests/test_enrichment.py`, patrón SQLite in-memory + `StaticPool`):
  guardar y leer por sesión; por serie; última escritura gana (`hijos=1` luego
  `hijos=2` → `2`); **criterio 3**: nueva instancia de repo/service sobre el
  MISMO engine (simula reinicio) → los campos siguen; campo fuera de whitelist →
  ValueError; valor inválido (`hijos="perro"`) → ValueError; serie None no rompe
  `fields_for`.

**Impacto en contrato API (front↔back)**: No — capa de datos interna.
**Acciones**:
1. TDD-light: tests primero (rojo: módulos no existen).
2. Modelo + repo + service + registro en `init_db`.
3. Suite completa verde.

**Pruebas / verificación**: pytest completo verde; ningún test existente editado.
**Riesgos**: crear el engine global por accidente en tests → mitigado con el
patrón perezoso de C3 (ya probado dos veces).

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `feat(back): persist enriched profile fields per session and serie`

---

## Fase 2 — Tool `enriquecer_perfil` → perfil → motor (criterios 1 y 2)

**Proyecto**: backend
**Objetivo**: el agente captura datos tipados en conversación, quedan en BD y el
motor los usa EN EL MISMO FLUJO con razones que los citan.
**Archivos afectados**:
- [conversation.py (schemas)](backend/app/schemas/conversation.py) —
  `ProfileData` gana `children_count: Optional[int] = None` (aditivo).
- [agent_tools.py](backend/app/services/agent_tools.py) —
  - Nueva `_ENRIQUECER_PERFIL_DECLARATION`: tool `enriquecer_perfil(campo,
    valor)`; description clara para el LLM ("cuando el cliente mencione un dato
    personal nuevo — hijos, mascota, vehículo, crédito, ocupación, hábitos —
    regístralo ANTES de recomendar; un dato por llamada"); `campo` con enum de la
    whitelist; `valor` string.
  - Handler `_enriquecer_perfil`: llama `EnrichmentService.record(...)` (session
    y serie del `ctx` si se conoce — guardar `document_number` en `ToolContext`
    al perfilarse para tenerlo aquí); **mapea al perfil en memoria**: `hijos` →
    `has_children` (`n>=1`) + `children_count=n`; `vehiculo` → `has_vehicle`;
    `credito` → `has_credit`; `tipo_vivienda` → `property_type`; `mascota/
    fumador/ocupacion` → solo persisten (sin señal aún). Devuelve `{campo,
    valor, persistido: true, profile}`; campo/valor inválido → `{"error": ...}`
    controlado. Registrar la tool en `AGENT_TOOLS`.
  - `ToolContext` gana `document_number: str | None = None` (aditivo; se setea en
    `_perfilar_cliente`).
- [propensity.py](backend/app/services/propensity.py) — SOLO la `evidence` de la
  regla `dependents`: si el perfil trae `children_count`, citar el número
  ("2 hijos declarados"); si no, el texto actual. (Peso y condición intactos.)
- [orchestrator.py](backend/app/services/orchestrator.py) — una línea en el
  SYSTEM_PROMPT (sección de reglas blandas, no numeradas como DURAS): cuando el
  cliente mencione un dato personal nuevo, usar `enriquecer_perfil` antes de
  recomendar. El orquestador ya reconstruye `ctx` por turno — sin más cambios.
- Tests (ampliar `tests/test_agent_tools.py` + `tests/test_enrichment.py`):
  - **Criterio 1 literal**: dos llamadas a la tool (`hijos=2`, `mascota=perro`)
    con engine in-memory → `fields_for_session` devuelve `{"hijos": "2",
    "mascota": "perro"}` y `ctx.profile.children_count == 2`,
    `ctx.profile.has_children is True`.
  - **Criterio 2**: ctx con perfil de hogar (recomendación hogar) →
    `enriquecer_perfil(campo="vehiculo", valor="si")` → `recomendar_seguro` →
    `movilidad-auto` con razón `vehicle_declared` (el dato enriquecido cambió el
    producto y la razón lo cita).
  - Evidencia con número: perfil con `children_count=2` → razón `dependents`
    contiene "2".
  - Negativos: campo desconocido → `{"error"}` sin excepción; `hijos="perro"` →
    `{"error"}`; tool sin sesión previa no revienta.
  - Declaración: `enriquecer_perfil` aparece en `tool_declarations()` con enum
    de campos.

**Impacto en contrato API (front↔back)**: Sí — **aditivo e inocuo**:
`ProfileData` gana la clave opcional `children_count` (null por defecto) en las
respuestas que incluyen `profile`; el frontend no la lee — cero cambios en front.
Rutas/status intactos.
**Acciones**:
1. TDD-light: tests primero (rojo: la tool no existe).
2. Implementar declaración + handler + mapeo + evidencia + prompt.
3. Suite completa verde.

**Pruebas / verificación**: pytest completo verde. Manual opcional (requiere
`GEMINI_API_KEY`, se omite en `/launch-plan`): chat "tengo dos hijos y un perro"
→ el agente llama la tool dos veces y la recomendación pasa a vida citando los
hijos.
**Riesgos**: el LLM podría no llamar la tool (prompt) — mitigación: la
declaración con description imperativa + la línea del system prompt; el criterio
se prueba a nivel tool (determinista), el comportamiento LLM se verifica manual.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 3 sin aprobación del usuario.
**Commit sugerido**: `feat(back): capture enriched profile data in conversation`

---

## Fase 3 — Memoria cross-sesión por SERIE + doc

**Proyecto**: backend
**Objetivo**: "el sistema aprende de cada conversación" — una SERIE conocida
recupera en su próxima sesión (cualquier canal) lo enriquecido antes, sin volver
a preguntar.
**Archivos afectados**:
- [agent_tools.py](backend/app/services/agent_tools.py) — `_perfilar_cliente`:
  con `document_number`, tras resolver el perfil base, consulta
  `EnrichmentService.fields_for(session_id, serie)` y aplica el mapeo de F2 con
  la prioridad de la decisión (c): **declarado ahora > enriquecido previo > base
  real/sintética** (el enriquecido solo llena huecos `None` del declarado, y pisa
  al sintético). Setea `ctx.document_number`.
- Tests (ampliar `tests/test_agent_tools.py`):
  - Sesión A: `perfilar_cliente(document_number="S1")` + `enriquecer_perfil
    (vehiculo=si)`; sesión B nueva (otro `ToolContext`, mismo engine):
    `perfilar_cliente(document_number="S1")` → `ctx.profile.has_vehicle is True`
    **sin declararlo** y `recomendar_seguro` → movilidad (aprendizaje
    cross-sesión demostrable sin LLM).
  - Prioridad: base sint dice `has_vehicle=True`, enriquecido previo dice
    `vehiculo=no` → gana el enriquecido (`False`); y si además lo declara ahora
    (`has_vehicle=True` en args) → gana lo declarado.
  - Sin documento → nada cambia (los tests existentes de perfil declarado siguen
    verdes sin editar).
- [backend/README.md](backend/README.md) — sección corta "Perfil enriquecido
  (A4)": tabla, whitelist, prioridad de fusión, y que G3/panel pueden leerla.
  (La escribe el orquestador/usuario en este checkpoint — fuera del ámbito del
  implementer.)

**Impacto en contrato API (front↔back)**: Sí — **valores, no shape**: un afiliado
recurrente puede llegar con el perfil ya enriquecido en `profile` desde el primer
turno. Frontend sin cambios.
**Acciones**:
1. TDD-light: tests de cross-sesión y prioridad primero.
2. Implementar la fusión en `_perfilar_cliente`.
3. README (orquestador).
4. Suite completa verde.

**Pruebas / verificación**: pytest completo verde; negativo cubierto (sin
documento, sin BD → fallback intacto). Manual opcional con BD: dos sesiones REST
con el mismo `document_number` → la segunda arranca sabiendo lo de la primera.
**Riesgos**: en tests, la tool resuelve el engine global — usar el mismo
monkeypatch de `db.get_engine` ya probado en C2/F3 (patrón existente en
[test_agent_tools.py](backend/tests/test_agent_tools.py)).

🛑 **CHECKPOINT** — fin del plan.
**Commit sugerido**: `feat(back): reuse enriched fields across sessions by serie`

---

## Deuda / fuera de alcance (anotada para el vault)

- **Categoría Mascotas**: `mascota` se captura y persiste pero no puntúa — falta
  el producto en el catálogo (nota de B2: solo si sobra tiempo). Cuando exista:
  1 producto JSON + 1 regla en `CATEGORY_RULES` + señal en el mapeo.
- **`fumador`/`ocupacion` como señales**: persisten desde A4; puntuarlas es
  calibración futura (B5/Matriz — ocupaciones de alto riesgo, recargo fumador).
- **Extracción estructurada post-turno** (alternativa a la tool que sugería la
  tarea): descartada por ahora — la tool es determinista, testeable y no gasta
  un segundo llamado al LLM por turno.
- **G3/panel leyendo `perfil_enriquecido`**: la tabla queda lista; el query/vista
  es de G3.
- **UI del perfil enriquecido en el chat** (mostrar "esto sé de ti"): idea de
  demo, no bloqueante.
