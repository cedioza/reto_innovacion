# Plan — G4: Vista de clientes con búsqueda y ficha de detalle · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-26 · **Tipo**: plan de implementación por fases.
> **Base**: [20260725-g3-disparador-proactivo-base-real.plan.md](.claude/analysis/plans/20260725-g3-disparador-proactivo-base-real.plan.md)
> (panel + `ProactiveService`), [20260725-a4-enriquecimiento-perfil-conversacion.plan.md](.claude/analysis/plans/20260725-a4-enriquecimiento-perfil-conversacion.plan.md)
> (tabla `perfil_enriquecido`), [20260725-e1-handoff-correo-aseguradora-simulada.plan.md](.claude/analysis/plans/20260725-e1-handoff-correo-aseguradora-simulada.plan.md)
> (estado `finalizada_demo` = "compró"), [20260726-a6-nombre-cliente-saludo.plan.md](.claude/analysis/plans/20260726-a6-nombre-cliente-saludo.plan.md)
> (campo `nombre` enriquecido — aún NO implementado).
> **Proyectos afectados**: ambos (backend primero).
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

Una pestaña "Clientes" en el panel de negocio donde Colsubsidio consulta a las
personas que pasaron por el funnel: **buscador** (por SERIE, por correo capturado
en el consentimiento y — cuando A6 exista — por nombre) y **ficha de detalle**
por cliente con: badge **afiliado/no afiliado** (fuente `base` vs `declarado`),
perfil fusionado (base + enriquecido en conversación, cada dato con su **origen**
y las columnas `sint_` marcadas como sintéticas), qué seguros se le **ofrecieron**
(recomendaciones + disparos proactivos), cuáles **cotizó** y cuáles **compró**
(`finalizada_demo` = compró en el MVP), con acceso a las conversaciones asociadas.

Contexto de la tarea (vault G4): 🔪 recortable — es valor para el pitch de piloto
("Colsubsidio ve a cada cliente"), no para el video del domingo.

## Contexto / hallazgos del análisis

**El eslabón que falta: la conversación no persiste la SERIE.**

- [ConversationResponse](backend/app/schemas/conversation.py#L104) no tiene campo
  `serie`/`document_number`: [ConversationService.create](backend/app/services/conversation.py#L47)
  recibe `document_number`, lo usa para armar el perfil y **lo descarta**.
- En el orquestador, [ToolContext.document_number](backend/app/services/agent_tools.py#L61)
  se setea solo si `perfilar_cliente` corre **en ese turno**
  ([agent_tools.py:175-177](backend/app/services/agent_tools.py#L175-L177));
  [_ctx_from_session](backend/app/services/orchestrator.py#L101-L119) **no lo
  restaura** entre turnos y [_sync_ctx_to_session](backend/app/services/orchestrator.py#L215-L248)
  **no lo vuelca** a la sesión. Consecuencia extra (bug latente): en un turno
  posterior a la identificación, [`_enriquecer_perfil` graba con `ctx.document_number = None`](backend/app/services/agent_tools.py#L615)
  y se pierde la memoria cross-sesión por serie.
- El disparo proactivo ([ProactiveService.trigger](backend/app/services/proactive.py#L161-L220))
  crea la sesión con la serie y la devuelve en el response… pero tampoco queda
  persistida en la conversación.
- Hoy la única asociación serie↔sesión persistida son las filas de
  [perfil_enriquecido](backend/app/models/enriched_field.py#L18-L28) (parcial, solo
  si hubo enriquecimiento en el mismo turno de la identificación).

**Qué hay para agregar por cliente:**

- `afiliados` ([AffiliateRecord](backend/app/models/affiliate_record.py#L26-L54)):
  perfil base por serie, con columnas reales y sintéticas (`sint_*`) ya separadas.
  Lookup existente: [AffiliateRepository.find_by_document](backend/app/repositories/affiliates.py#L156).
- `conversaciones` ([ConversationRecord](backend/app/models/conversation.py#L16-L28)):
  el documento completo (`ConversationResponse`: mensajes con timestamp,
  `recommendation` con `reasons`, `quote`, `application`) va serializado en la
  columna `data` (JSON); `created_at`/`updated_at` y `canal` son columnas propias.
- `solicitudes` ([ApplicationRecord](backend/app/models/application.py#L14-L26)):
  `data` = [ConsentedApplication](backend/app/schemas/conversation.py#L78-L88) con
  `email`, `product_id`, `state` (`ready_for_payment` → solicitada,
  `finalizada_demo` → comprada vía [ConsentService.finalize_by_token](backend/app/services/consent.py#L114-L130)).
- `perfil_enriquecido`: EAV sesión/serie/campo/valor; whitelist en
  [EnrichmentService.ALLOWED_FIELDS](backend/app/services/enrichment.py#L50-L58)
  (**sin `nombre` todavía** — llega con A6).

**Los repositorios no tienen listados.** [ConversationRepository](backend/app/repositories/conversations.py#L32),
[ApplicationRepository](backend/app/repositories/applications.py#L38) y
[EnrichedProfileRepository](backend/app/repositories/enriched_profile.py#L23) solo
tienen `find`/`count` por clave — agregar métodos de listado es prerequisito.

**Panel actual (G3, no G1/G2).** El router [panel.py](backend/app/api/routes/panel.py)
solo expone `/panel/cohortes` y `/panel/cohortes/{id}/disparar`; los endpoints de
G1 (`/panel/solicitudes`, `/panel/metricas`) **no existen** y la vista
[PanelView.vue](frontend/src/features/panel/PanelView.vue) es solo cohortes — no
hay pestañas ni componentes de detalle de G2 para reusar. Este plan es
autocontenido: construye únicamente los 2 endpoints de clientes que G4 necesita y
reutiliza el `GET /api/v1/conversations/{session_id}` existente
([conversations.py:30](backend/app/api/routes/conversations.py#L30),
[api.js `getConversation`](frontend/src/shared/services/api.js#L51-L53)) para la
transcripción.

**Restricción de esquema (sin Alembic).** Las tablas se crean con
`SQLModel.metadata.create_all` ([main.py:19-23](backend/app/main.py#L19-L23));
`create_all` **no altera tablas existentes**, así que agregar una columna nueva a
`ConversationRecord` rompería las BD ya creadas (SQLite/Postgres). La serie se
persiste **dentro del JSON `data`** (campo aditivo en `ConversationResponse`),
sin tocar el esquema físico.

**Decisiones tomadas en el análisis** (para no adivinar en ejecución):

- `cliente_id` = `serie` para afiliados; para prospectos sin serie, el
  `session_id` de su conversación (no hay forma de agrupar sesiones anónimas
  entre sí — cada sesión anónima es un prospecto).
- Búsqueda: SERIE por match exacto; correo y nombre por substring
  case-insensitive. `q` vacío = listar todos (limitado, más recientes primero).
- "Ofrecido" = toda sesión con `recommendation` (cubre chat y disparo proactivo:
  ambos la persisten). "Proactivo" se marca cuando el primer mensaje de la sesión
  es del asistente (los disparos abren la conversación hablando ellos).
- "Cotizó" = sesión con `quote`; "compró" = solicitud con `state == finalizada_demo`.
- La búsqueda por nombre queda implementada contra el campo enriquecido `nombre`:
  hoy no matcheará nada (A6 pendiente) y empezará a funcionar sola cuando A6 entre.

## Decisiones pendientes (bloqueantes)

(ninguna) — pero dos avisos de alcance:

1. La tarea está marcada 🔪 **recortable, no entra al freeze del domingo**:
   confirmar que vale la pena ejecutarla ahora frente a lo que falte del video.
2. El criterio "buscar por nombre" solo dará resultados cuando
   [A6](.claude/analysis/plans/20260726-a6-nombre-cliente-saludo.plan.md) esté
   implementado (hoy `nombre` no se captura).

## Principios

- Verde por fase: `pytest` (backend) / `npm run build` (frontend) al cierre de cada una.
- Backend primero: el frontend solo consume endpoints que ya existen.
- Contrato HTTP explícito: shapes JSON definidos en este plan; solo rutas nuevas
  bajo `/api/v1/panel/` (aditivo, nada existente cambia).
- Aditivo antes que destructivo: campo `serie` opcional en el JSON, sin
  migraciones de esquema, sin tocar respuestas existentes.
- Alcance mínimo, sin dependencias nuevas; escaneo en Python (no SQL sobre JSON) —
  a escala hackathon (decenas de conversaciones) es suficiente.
- Capas obligatorias del backend: `api → services → repositories → models`; cada
  service pide datos de otras entidades a su service, nunca al repo ajeno.
- Panel sin auth (deuda aceptada en G1).

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | ambos | Ninguno | 5m | _(sin commit)_ |
| 1 | Persistir la SERIE en la sesión de conversación | backend | Aditivo | 25m | `feat(back): persist serie on conversation sessions` |
| 2 | Métodos de listado en repositorios y services | backend | Aditivo | 25m | `feat(back): add listing methods for client aggregation` |
| 3 | Endpoints `/panel/clientes` (búsqueda + ficha) | backend | Aditivo | 45m | `feat(back): add panel clientes search and detail endpoints` |
| 4 | Pestañas en el panel + tabla de clientes con buscador | frontend | Medio (reorganiza PanelView) | 35m | `feat(front): add clientes tab with search to panel` |
| 5 | Ficha de detalle (drawer) con origen de datos y funnel | frontend | Aditivo | 45m | `feat(front): client detail drawer with origins and offers` |

Total estimado: ~3h. **Si hay que recortar**: la Fase 5 puede reducirse (ficha sin
acceso a transcripción, solo listas) o aplazarse; las Fases 1-2 son valiosas por sí
solas (arreglan la memoria cross-sesión por serie y habilitan G5).

---

## Fase 0 — Pre-flight (read-only / verificación)
**Proyecto**: ambos
**Objetivo**: partir de un estado verde conocido.
**Archivos afectados**: ninguno (solo lectura).
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. (backend) Desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` — anotar el estado base.
2. (frontend) Desde `frontend/`: `npm run build` — debe terminar OK.
3. (backend) Verificar que la BD de dev tiene datos: `afiliados` cargada y al menos
   una conversación/solicitud (si no, correr el seed de demo
   [seed_demo.py](backend/app/scripts/seed_demo.py) ayuda a probar manualmente).

**Pruebas / verificación**: las de arriba.
**Riesgos**: si el pytest base ya está rojo, resolver antes de arrancar (no es de esta feature).

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit)_

---

## Fase 1 — Persistir la SERIE en la sesión de conversación
**Proyecto**: backend
**Objetivo**: que toda sesión identificada (por creación con documento, por disparo
proactivo o por `perfilar_cliente` a mitad de conversación) quede asociada a su
SERIE de forma durable — el cimiento de la agrupación por cliente.
**Archivos afectados**:
- [backend/app/schemas/conversation.py](backend/app/schemas/conversation.py#L104) — `ConversationResponse`
- [backend/app/services/conversation.py](backend/app/services/conversation.py#L47) — `create`
- [backend/app/services/orchestrator.py](backend/app/services/orchestrator.py#L101) — `_ctx_from_session`, `_sync_ctx_to_session`
- [backend/tests/](backend/tests/) — `test_conversation_service.py`, `test_orchestrator.py` (ampliar)

**Impacto en contrato API (front↔back)**: Sí, aditivo e inocuo — `ConversationResponse`
gana el campo opcional `serie` (default `None`) que el frontend puede ignorar
(no se actualiza nada del otro lado; ninguna fase lo consume desde el chat).
**Acciones**:
1. Agregar `serie: Optional[str] = None` a `ConversationResponse` — al persistirse
   el documento completo en `data`, no hay migración de esquema.
2. En `ConversationService.create`: si `body.document_number` resolvió un afiliado
   real (`lookup` no-None), setear `session.serie = body.document_number`. Esto
   cubre también el disparo proactivo, que crea vía `create(ConversationCreate(document_number=serie))`
   ([proactive.py:176](backend/app/services/proactive.py#L176)).
3. En `_ctx_from_session`: restaurar `document_number=session.serie` al construir
   el `ToolContext` (arregla el bug latente de enriquecimiento sin serie en turnos
   posteriores a la identificación).
4. En `_sync_ctx_to_session`: si `ctx.document_number` es no-None y el afiliado
   existe (la tool ya lo validó — basta `ctx.profile.source == "base"`), volcar
   `session.serie = ctx.document_number`.
5. Tests: (a) `create` con documento afiliado → `serie` persistida y presente al
   releer del repo; (b) `create` sin documento → `serie is None`; (c) orquestador:
   sesión con `serie` persistida → el `ToolContext` del siguiente turno la trae;
   (d) turno donde `perfilar_cliente` identifica → la sesión re-leída tiene `serie`.

**Pruebas / verificación**: `.venv\Scripts\python.exe -m pytest -q` en verde;
sesiones viejas (JSON sin el campo) siguen validando (campo opcional con default).
**Riesgos**: ninguno relevante — campo aditivo con default; los documentos ya
persistidos validan sin él.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `feat(back): persist serie on conversation sessions`

---

## Fase 2 — Métodos de listado en repositorios y services
**Proyecto**: backend
**Objetivo**: poder enumerar conversaciones, solicitudes y perfil enriquecido para
agregarlos por cliente — respetando las capas (el service de clientes de la Fase 3
pedirá estos datos a cada service dueño, nunca a repos ajenos).
**Archivos afectados**:
- [backend/app/repositories/conversations.py](backend/app/repositories/conversations.py) — `list_all()`
- [backend/app/repositories/applications.py](backend/app/repositories/applications.py) — `list_all()`
- [backend/app/repositories/enriched_profile.py](backend/app/repositories/enriched_profile.py) — `list_all()`
- [backend/app/services/conversation.py](backend/app/services/conversation.py) — exponer `list_sessions()`
- [backend/app/services/consent.py](backend/app/services/consent.py) — exponer `list_applications()`
- [backend/app/services/enrichment.py](backend/app/services/enrichment.py) — exponer `all_fields()`
- [backend/tests/](backend/tests/) — `test_conversation_repository.py`, `test_applications_repository.py`, `test_enrichment.py` (ampliar)

**Impacto en contrato API (front↔back)**: No (interno; ningún endpoint cambia).
**Acciones**:
1. `ConversationRepository.list_all()` → lista de dicts
   `{session, canal, created_at, updated_at}` donde `session` es el
   `ConversationResponse` validado desde `data` (los timestamps de columna se
   necesitan para "última actividad"; una fila cuyo `data` no valide se salta con
   warning, nunca rompe el listado). Orden: `updated_at` descendente.
2. `ApplicationRepository.list_all()` → `list[ConsentedApplication]` (mismo
   patrón defensivo).
3. `EnrichedProfileRepository.list_all()` → todas las filas
   (`session_id, serie, campo, valor`) en orden de `id` ascendente (la semántica
   "última escritura gana" la resuelve el consumidor, igual que
   [`fields_for_session`](backend/app/repositories/enriched_profile.py#L41-L49)).
4. Exponer en cada service dueño: `ConversationService.list_sessions()`,
   `ConsentService.list_applications()`, `EnrichmentService.all_fields()` —
   delegación directa, sin lógica.
5. Tests por repo: sembrar 2-3 filas (engine SQLite de test, patrón de
   [test_conversation_repository.py](backend/tests/test_conversation_repository.py))
   y verificar listado, orden y tolerancia a una fila corrupta.

**Pruebas / verificación**: `.venv\Scripts\python.exe -m pytest -q` en verde.
**Riesgos**: escaneo completo por request — aceptado a escala hackathon (documentarlo
en el docstring del método para que nadie lo confunda con un patrón de producción).

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 3 sin aprobación del usuario.
**Commit sugerido**: `feat(back): add listing methods for client aggregation`

---

## Fase 3 — Endpoints `/panel/clientes` (búsqueda + ficha)
**Proyecto**: backend
**Objetivo**: la API read-only que el panel consume: listado buscable de clientes y
ficha de detalle con perfil fusionado (con origen), funnel ofrecido/cotizado/comprado
y conversaciones asociadas.
**Archivos afectados**:
- `backend/app/services/panel_clientes.py` — **nuevo** `PanelClientesService`
- [backend/app/schemas/panel.py](backend/app/schemas/panel.py) — DTOs nuevos
- [backend/app/api/routes/panel.py](backend/app/api/routes/panel.py) — 2 rutas nuevas
- `backend/tests/test_panel_clientes.py` — **nuevo**

**Impacto en contrato API (front↔back)**: **Sí** — dos rutas nuevas que el frontend
consume en las Fases 4 y 5:

`GET /api/v1/panel/clientes?q=<texto>` → `200`:
```json
{
  "total": 2,
  "clientes": [
    {
      "cliente_id": "1041886",
      "serie": "1041886",
      "afiliado": true,
      "nombre": null,
      "email": "ana@mail.com",
      "conversaciones": 2,
      "solicitudes": 1,
      "ultimo_estado": "finalizada_demo",
      "ultima_actividad": "2026-07-26T14:03:00+00:00"
    },
    {
      "cliente_id": "<session_id>",
      "serie": null,
      "afiliado": false,
      "nombre": null, "email": null,
      "conversaciones": 1, "solicitudes": 0,
      "ultimo_estado": "quote_ready",
      "ultima_actividad": "..."
    }
  ]
}
```

`GET /api/v1/panel/clientes/{cliente_id}` → `200`:
```json
{
  "cliente_id": "1041886",
  "serie": "1041886",
  "afiliado": true,
  "fuente_perfil": "base",
  "perfil": [
    {"campo": "age_range", "valor": "26-40", "origen": "base"},
    {"campo": "sint_tiene_vehiculo", "valor": "true", "origen": "sintetico"},
    {"campo": "hijos", "valor": "2", "origen": "conversacion"}
  ],
  "ofertas": [
    {"session_id": "...", "product_id": "movilidad-conductor", "product_name": "...",
     "tipo": "proactivo", "fecha": "..."}
  ],
  "cotizaciones": [
    {"session_id": "...", "product_id": "...", "product_name": "...",
     "monthly_premium": 58000, "fecha": "..."}
  ],
  "solicitudes": [
    {"session_id": "...", "product_id": "...", "estado": "finalizada_demo",
     "comprado": true, "email": "ana@mail.com", "fecha": "..."}
  ],
  "conversaciones": [
    {"session_id": "...", "canal": "web", "estado": "finalizada_demo",
     "mensajes": 14, "inicio": "...", "ultima_actividad": "..."}
  ]
}
```
`404` si `cliente_id` no matchea ni serie conocida ni sesión. Sin params
obligatorios → no hay 422 que diseñar; `q` vacío o ausente lista todos.
**Acciones**:
1. `PanelClientesService` compone **services** (regla de capas):
   `ConversationService.list_sessions()`, `ConsentService.list_applications()`,
   `EnrichmentService.all_fields()`, `AffiliateService.lookup()`. Agrupa por
   `cliente_id` (serie si la sesión la tiene — Fase 1 —, si no `session_id`;
   las filas de `perfil_enriquecido` con serie complementan la asociación para
   datos históricos previos a la Fase 1).
2. Búsqueda: serie exacta; email (de `ConsentedApplication.email`) y nombre
   (campo enriquecido `nombre`, cuando exista) por substring case-insensitive;
   `q` vacío → todos, orden por `ultima_actividad` descendente.
3. Ficha — perfil fusionado con origen: columnas reales de
   [AffiliateRecord](backend/app/models/affiliate_record.py#L31-L46) → `"base"`,
   columnas `sint_*` → `"sintetico"`, campos de `perfil_enriquecido` →
   `"conversacion"` (regla existente: sesión pisa a serie). Para prospectos, el
   `ProfileData` declarado de su sesión → `"declarado"`.
4. Funnel: ofertas = sesiones con `recommendation` (tipo `"proactivo"` si el
   primer mensaje es del asistente, `"recomendacion"` si no); cotizaciones =
   sesiones con `quote`; solicitudes = `ConsentedApplication` con
   `comprado = (state == "finalizada_demo")`. Fechas desde los timestamps de
   mensajes / `consent_timestamp` / columnas del registro.
5. DTOs en [schemas/panel.py](backend/app/schemas/panel.py) (mismo patrón del
   módulo: dicts planos del service validados por Pydantic al salir) y las 2
   rutas en [panel.py](backend/app/api/routes/panel.py) delegando al service;
   `404` vía `HTTPException` como en
   [`disparar_cohorte`](backend/app/api/routes/panel.py#L25-L29).
6. Tests (`test_panel_clientes.py`, con `TestClient` + engine sembrado):
   afiliado con conversación+solicitud aparece con sus campos y orígenes; buscar
   por email lo encuentra; prospecto sin serie aparece con `afiliado: false`;
   ruta negativa: `GET /panel/clientes/no-existe` → `404` (nunca 500);
   BD vacía → `200 {"total": 0, "clientes": []}`.

**Pruebas / verificación**: pytest en verde; manual: levantar uvicorn y
`curl "http://localhost:8000/api/v1/panel/clientes?q=..."` contra datos del seed.
**Riesgos**: heurística "proactivo = abre el asistente" es aproximada (aceptada y
documentada); rendimiento del escaneo (aceptado, ver Fase 2).

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 4 sin aprobación del usuario.
La Fase 3 cambia el contrato (2 rutas nuevas): el frontend las consume en las
Fases 4 (listado) y 5 (ficha).
**Commit sugerido**: `feat(back): add panel clientes search and detail endpoints`

---

## Fase 4 — Pestañas en el panel + tabla de clientes con buscador
**Proyecto**: frontend
**Objetivo**: el panel gana estructura de pestañas (Cohortes | Clientes) y la
pestaña Clientes muestra la tabla buscable consumiendo `GET /panel/clientes`.
**Archivos afectados**:
- [frontend/src/features/panel/PanelView.vue](frontend/src/features/panel/PanelView.vue) — pestañas; lo actual pasa a ser la pestaña "Cohortes"
- `frontend/src/features/panel/components/ClientesTab.vue` — **nuevo** (buscador + tabla)
- `frontend/src/features/panel/composables/useClientes.js` — **nuevo**
- [frontend/src/shared/services/api.js](frontend/src/shared/services/api.js) — `getPanelClientes(q)`, `getPanelCliente(clienteId)`

**Impacto en contrato API (front↔back)**: Sí — consume las rutas creadas en la
Fase 3 (ningún cambio nuevo de contrato; el otro lado ya está hecho).
**Acciones**:
1. Reorganizar `PanelView.vue` con dos pestañas locales (estado `ref`, sin router
   nuevo ni dependencia de tabs): "Cohortes" envuelve el contenido actual tal
   cual (mismo `usePanel`), "Clientes" monta `ClientesTab.vue`. La feature sigue
   autocontenida en `features/panel/`.
2. `useClientes.js` (patrón de [usePanel.js](frontend/src/features/panel/composables/usePanel.js)):
   estado `clientes/total/isLoading/error/q`, carga inicial, búsqueda con
   debounce (~300 ms, sin librerías) y `reintentar()`.
3. `ClientesTab.vue`: input de búsqueda (placeholder "SERIE, correo o nombre"),
   tabla con columnas SERIE/afiliado (badge)/correo/conversaciones/solicitudes/
   último estado/última actividad, estados de carga, vacío ("sin resultados") y
   error con botón reintentar (API caída → mensaje, no pantalla rota — patrón
   existente del panel).
4. `api.js`: agregar las dos funciones nuevas (la de ficha se usa en Fase 5,
   entra aquí para dejar el servicio completo), con `encodeURIComponent(q)`.

**Pruebas / verificación**: `npm run build` OK; manual con ambos servidores:
la pestaña Cohortes sigue funcionando igual; buscar una SERIE del seed la
encuentra; con el backend apagado la pestaña muestra el error y el botón
reintentar.
**Riesgos**: regresión visual del panel al introducir pestañas — mantener intacto
el markup de cohortes (solo envolverlo).

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 5 sin aprobación del usuario.
**Commit sugerido**: `feat(front): add clientes tab with search to panel`

---

## Fase 5 — Ficha de detalle (drawer) con origen de datos y funnel
**Proyecto**: frontend
**Objetivo**: clic en una fila abre la ficha del cliente: badge afiliado/no
afiliado, perfil fusionado con el origen de cada dato (y los sintéticos
marcados), ofrecidos vs cotizados vs comprados, y acceso a las conversaciones.
**Archivos afectados**:
- `frontend/src/features/panel/components/ClienteDrawer.vue` — **nuevo**
- `frontend/src/features/panel/components/ClientesTab.vue` — abrir el drawer
- `frontend/src/features/panel/composables/useClientes.js` — estado de ficha (`ficha`, `isLoadingFicha`, `errorFicha`, `abrirFicha`, `cerrarFicha`)

**Impacto en contrato API (front↔back)**: Sí — consume `GET /panel/clientes/{id}`
(Fase 3) y el ya existente `GET /api/v1/conversations/{session_id}`
([api.js `getConversation`](frontend/src/shared/services/api.js#L51-L53)) para la
transcripción. Nada nuevo del lado del backend.
**Acciones**:
1. `ClienteDrawer.vue` (overlay lateral, CSS propio del feature — sin librerías):
   - Cabecera: SERIE (o "Prospecto — sesión abreviada"), badge
     `afiliado (base)` / `no afiliado (declarado)`.
   - Sección Perfil: lista campo/valor con chip de origen (`base` /
     `conversación` / `declarado` / `sintético` — este último con estilo de
     advertencia, decisión de transparencia del equipo).
   - Sección Funnel: tres bloques — Ofrecidos (producto + tipo
     recomendación/proactivo + fecha), Cotizados (producto + prima mensual
     formateada COP), Solicitudes (producto + estado con badge "comprado" si
     `comprado`, correo y fecha).
   - Sección Conversaciones: una fila por sesión (canal, estado, nº de
     mensajes, última actividad) con "ver transcripción" que expande inline la
     conversación traída con `getConversation(session_id)` (solo mensajes
     `type === "text"`, rol y hora).
2. Estados de carga/error del drawer con reintento; cerrar con ✕ y con `Esc`.
3. Caso negativo: ficha `404` (cliente desapareció) → mensaje "cliente no
   encontrado" dentro del drawer, la tabla sigue viva.

**Pruebas / verificación**: `npm run build` OK; manual e2e con seed: buscar SERIE
real → ficha completa con orígenes y badge; prospecto declarado → ficha lo
distingue; solicitud finalizada vía página de aseguradora → aparece "comprado";
"ver transcripción" muestra la conversación; backend caído a mitad → error
manejado.
**Riesgos**: es la fase más recortable — si aprieta el tiempo, dejar la
transcripción fuera (enlace deshabilitado) y entregar solo perfil + funnel.

🛑 **CHECKPOINT** — Fin del plan.
**Commit sugerido**: `feat(front): client detail drawer with origins and offers`
