# Plan — G5: Dashboard funnel de ventas por producto · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-26 · **Tipo**: plan de implementación por fases.
> **Base**:
> [20260725-g3-disparador-proactivo-base-real.plan.md](.claude/analysis/plans/20260725-g3-disparador-proactivo-base-real.plan.md)
> (✅ en master: router `/panel` + feature `panel/` del front — G5 agrega una sección
> al mismo panel),
> [20260725-h4-seed-y-guiones-demo.plan.md](.claude/analysis/plans/20260725-h4-seed-y-guiones-demo.plan.md)
> (✅ en master: `seed_demo` siembra 5 ventas + 2 en curso — la garantía de que el
> funnel nunca aparece vacío y el fixture natural de los tests),
> [20260725-c3-conversaciones-solicitudes-postgres.plan.md](.claude/analysis/plans/20260725-c3-conversaciones-solicitudes-postgres.plan.md)
> (✅ en master: tabla `conversaciones` con el documento completo en `data` — la única
> fuente que el funnel necesita) y
> [20260725-b5-preguntas-por-categoria-matriz.plan.md](.claude/analysis/plans/20260725-b5-preguntas-por-categoria-matriz.plan.md)
> (✅ en master: `ProfileData.source` "base"|"declarado" — el corte afiliado/no
> afiliado sale de ahí).
> Tarea del vault: `07 - Tareas/Feature G - Panel y proactivo/G5 - Dashboard funnel de ventas por producto.md`
> (depende de **G1 — aún pendiente, ver decisión 1**; no bloquea a nadie; capa ambas;
> estimación 3h; **🔪 recortable, no entra al freeze del domingo**).
> **Proyectos afectados**: ambos (backend primero, luego frontend).
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

Una sección **"Funnel de ventas"** en el panel de negocio con números que se leen de
un vistazo: por cada uno de los 5 seguros del catálogo, el funnel
**recomendado → cotizado → consentimiento → comprado** (más el total global de
conversaciones como boca del embudo), tasas de conversión entre etapas, comparativo
de qué productos se compran y cuáles se caen en el camino, y el corte agregado
**afiliado (perfil de la base) vs no afiliado (perfil declarado)**. "Hogar convierte
34%, Movilidad se cae en la cotización."

Con el seed de H4 cargado (`python -m app.scripts.seed_demo`), ninguna sección del
dashboard queda vacía en el primer acceso del jurado.

## Contexto / hallazgos del análisis

**G1 NO está hecho — `GET /panel/metricas` no existe.** El router del panel
([panel.py](backend/app/api/routes/panel.py)) solo expone lo de G3: `GET
/panel/cohortes` y `POST /panel/cohortes/{id}/disparar`
([panel.py:15-29](backend/app/api/routes/panel.py#L15-L29)). La tarea del vault dice
"extender `GET /panel/metricas`", pero no hay nada que extender: G5 **crea** ese
endpoint (ver Decisiones, punto 1). No hay plan previo de G1/G2 en
`.claude/analysis/plans/`.

**Todo lo que el funnel necesita vive en la tabla `conversaciones`.** La columna
`data` guarda el `ConversationResponse` completo
([conversations.py:39-60](backend/app/repositories/conversations.py#L39-L60)):
`state` ([conversation.py:8-14](backend/app/schemas/conversation.py#L8-L14)),
`recommendation.product_id`, `quote`, `application` y `profile`
([conversation.py:104-112](backend/app/schemas/conversation.py#L104-L112)). Las
etapas se derivan del documento, sin joins:
- *recomendado*: `recommendation is not None`
- *cotizado*: `quote is not None`
- *consentimiento*: `application is not None` o `state` ∈ {`awaiting_consent`,
  `ready_for_payment`, `finalizada_demo`}
- *comprado*: `state == finalizada_demo`

**El corte afiliado/no afiliado ya tiene señal en el dato.** B5 agregó
`ProfileData.source` ("base"|"declarado")
([conversation.py:39-44](backend/app/schemas/conversation.py#L39-L44)): `base` =
perfil armado desde la tabla de afiliados (afiliado reconocido), `declarado` = lo
contó el cliente en el chat. Conversaciones anteriores al campo (p. ej. las del seed
H4 actual) traen `source=None` → se cuentan como `declarado` (documentado en el
schema de respuesta; ver Decisiones, punto 2).

**Falta un método de listado en el repositorio.**
[conversations.py](backend/app/repositories/conversations.py) solo tiene
`save/find/delete/count` — la Fase 1 agrega `list_all()` (devuelve los documentos
validados, saltando filas corruptas sin tumbar el endpoint). Regla de capas: el
dueño de `ConversationRepository` es `ConversationService`
([conversation.py:43](backend/app/services/conversation.py#L43)), así que el service
nuevo del funnel **compone** `ConversationService` (patrón orquestador permitido por
[backend/CLAUDE.md](backend/CLAUDE.md)), nunca toca el repo directo.

**Patrones a copiar tal cual:**
- Service del panel: [proactive.py:106-159](backend/app/services/proactive.py#L106-L159)
  (`list_cohorts` devuelve dicts planos + `fuente: "postgres"|"sin_datos"` — el
  funnel replica ese contrato de `fuente`).
- Schemas del panel: [panel.py](backend/app/schemas/panel.py) (DTOs planos, nunca
  SQLModel expuesto).
- Los 5 productos SIEMPRE presentes: iterar `CatalogService().list_products()` como
  hace la propensión ([propensity.py:289-296](backend/app/services/propensity.py#L289-L296))
  — un producto sin ventas aparece con ceros, jamás desaparece (criterio de
  aceptación: distinguir cuáles NO se compraron).
- Front: feature `panel/` con composable + componentes
  ([PanelView.vue](frontend/src/features/panel/PanelView.vue),
  [usePanel.js](frontend/src/features/panel/composables/usePanel.js) — manejo de
  error + reintentar ya resuelto). HTTP solo vía
  [api.js](frontend/src/shared/services/api.js) (patrón `getPanelCohortes()` en
  [api.js:79-81](frontend/src/shared/services/api.js#L79-L81)).

**Fixture de tests gratis:** `app.scripts.seed_demo.sembrar(engine=...)` (H4) deja 5
ventas `finalizada_demo` (una por producto) + 1 `quote_ready` + 1 `awaiting_consent`
— exactamente las cifras que el test del funnel debe cuadrar
([seed_demo.py](backend/app/scripts/seed_demo.py),
[test_seed_demo.py](backend/tests/test_seed_demo.py) muestra el monkeypatch de
`db.get_engine`).

**Advertencia de producto (nota del vault):** la dueña del reto descartó "dashboard
como solución" — esto es evidencia de gestión para el piloto, sobrio y legible, sin
librería de charts (CSS puro, coherente con G2/G3). Nunca el centro del demo.

## Decisiones pendientes (bloqueantes)

(ninguna — tres defaults ajustables en los checkpoints:)

1. **G1 pendiente → G5 crea `GET /api/v1/panel/metricas`** con el funnel dentro. Las
   "métricas simples" que G1 prometía (conversaciones, cotizaciones, cierres,
   conversión) quedan subsumidas en los totales globales de esta respuesta; cuando
   alguien tome G1 le quedan solicitudes, detalle de conversación y atípicos, sobre
   el mismo router. Anotar la brecha en el vault al cerrar.
2. **`profile.source == None` cuenta como `declarado`** (datos previos al campo,
   incl. el seed H4 de hoy). Alternativa descartada: bucket "desconocido" — ruido
   visual para el jurado sin valor de negocio.
3. **Es tarea 🔪 recortable**: si el sábado aprieta, la Fase 2 (front) se puede
   aplazar y el endpoint queda listo para consumirse después — el backend solo ya
   deja demo-able el número por curl.

## Principios

- Verde por fase: `pytest -q` (backend) / `npm run build` (frontend).
- **Backend primero**: el front consume un endpoint que ya existe y está testeado.
- Contrato HTTP explícito: un solo endpoint nuevo, GET puro, shape documentado en
  este plan; las rutas existentes del panel no cambian.
- Aditivo, no destructivo: no se toca `cohortes`, ni el chat, ni el seed.
- Fuente de verdad única: tabla `conversaciones` — cada cifra cuadra contra el seed.
- Cero dependencias nuevas (barras con CSS, sin chart libs). Cero env vars nuevas.
- Filas corruptas en `data` se saltan y se loguean — el panel nunca responde 500 por
  un documento viejo.

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | ambos | Ninguno | 5m | _(sin commit)_ |
| 1 | Endpoint `GET /panel/metricas` con funnel por producto | backend | Aditivo | 45m | `feat(panel): add funnel metrics endpoint by product` |
| 2 | Sección "Funnel de ventas" en el panel | frontend | Aditivo | 50m | `feat(front): sales funnel dashboard in panel view` |

Total ≈ 1h40m (holgura frente a las 3h del vault; el resto es pulido visual si sobra).

---

## Fase 0 — Pre-flight (read-only)

**Proyecto**: ambos
**Objetivo**: base sana antes de tocar nada.
**Archivos afectados**: ninguno.
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Backend desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` en verde
   (los `*_live` se saltan sin API key).
2. Frontend desde `frontend/`: `npm run build` OK.
3. Confirmar rutas actuales del panel (solo cohortes/disparar) y que
   `python -m app.scripts.seed_demo --replace` corre en local (opcional, para la
   verificación manual de la Fase 2).

**Pruebas / verificación**: las de arriba.
**Riesgos**: ninguno (read-only).

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit)_

---

## Fase 1 — Endpoint `GET /panel/metricas` con funnel por producto

**Proyecto**: backend
**Objetivo**: la API entrega el funnel completo, calculado desde la tabla
`conversaciones`, con los 5 productos siempre presentes y el corte afiliado/no
afiliado.
**Archivos afectados**:
- [backend/app/repositories/conversations.py](backend/app/repositories/conversations.py)
  → `list_all()`
- [backend/app/services/conversation.py](backend/app/services/conversation.py)
  → `list_all()` (delegación al repo propio)
- `backend/app/services/` → nuevo `panel_metrics.py` (`PanelMetricsService`)
- [backend/app/schemas/panel.py](backend/app/schemas/panel.py) → DTOs del funnel
- [backend/app/api/routes/panel.py](backend/app/api/routes/panel.py) → `GET /metricas`
- `backend/tests/` → nuevo `test_panel_metricas.py`

**Impacto en contrato API (front↔back)**: **Sí — aditivo.** Ruta nueva
`GET /api/v1/panel/metricas` (el otro lado se actualiza en la **Fase 2**). Shape:

```json
{
  "fuente": "postgres" | "sin_datos",
  "totales": {
    "conversaciones": 7, "recomendadas": 7, "cotizadas": 7,
    "con_consentimiento": 6, "compradas": 5, "conversion_global": 0.71
  },
  "funnel_por_producto": [
    {
      "product_id": "hogar-estandar", "product_name": "Seguro de Hogar",
      "categoria": "hogar",
      "etapas": {"recomendado": 2, "cotizado": 2, "consentimiento": 1, "comprado": 1},
      "tasas": {"cotizado_sobre_recomendado": 1.0,
                 "consentimiento_sobre_cotizado": 0.5,
                 "comprado_sobre_consentimiento": 1.0,
                 "comprado_sobre_recomendado": 0.5}
    }
  ],
  "corte_afiliacion": {
    "base": {"conversaciones": 0, "compradas": 0, "conversion": 0.0},
    "declarado": {"conversaciones": 7, "compradas": 5, "conversion": 0.71}
  }
}
```

**Acciones**:
1. `ConversationRepository.list_all() -> list[ConversationResponse]`: `select` de
   todos los `ConversationRecord`, `model_validate(record.data)` por fila con
   `try/except` — fila corrupta se loguea (`logger.warning`) y se salta, nunca
   revienta.
2. `ConversationService.list_all()` delega en su repo (una línea + docstring; el
   service es el único dueño del repo).
3. `PanelMetricsService` (nuevo, patrón de
   [proactive.py](backend/app/services/proactive.py)): compone
   `ConversationService` + `CatalogService`. `metricas() -> dict`:
   - Itera `CatalogService().list_products()` → una entrada por producto SIEMPRE
     (con ceros si no hay datos), en el orden del catálogo.
   - Clasifica cada conversación en etapas con los predicados del análisis
     (recomendado/cotizado/consentimiento/comprado); el producto sale de
     `recommendation.product_id`.
   - Tasas redondeadas a 2 decimales; divisor 0 → tasa 0.0 (nunca división por
     cero); `conversion_global = compradas / conversaciones`.
   - Corte: `profile.source == "base"` → bucket `base`; todo lo demás (incl. `None`
     o perfil ausente) → `declarado`.
   - `fuente`: `"postgres"` si hay ≥1 conversación, `"sin_datos"` si la tabla está
     vacía (mismo contrato que cohortes).
4. Schemas en [panel.py](backend/app/schemas/panel.py): `FunnelEtapas`,
   `FunnelTasas`, `FunnelProducto`, `MetricasTotales`, `CorteAfiliacion`,
   `MetricasResponse` — DTOs planos, con docstring que fije la semántica de
   `source=None → declarado`.
5. Router: `GET /metricas` con `response_model=MetricasResponse`, delgado como los
   existentes ([panel.py:15-17](backend/app/api/routes/panel.py#L15-L17)).
6. Tests (`test_panel_metricas.py`, `TestClient` + engine SQLite en memoria con
   monkeypatch de `db.get_engine`, patrón de
   [test_seed_demo.py](backend/tests/test_seed_demo.py)):
   - **DB vacía** → 200, `fuente="sin_datos"`, totales en cero, los 5 productos
     presentes con ceros (nunca 500 — la ruta negativa de un GET).
   - **Con el seed H4** (`sembrar()`): totales exactos (7 conversaciones, 5
     compradas, `conversion_global` 0.71), cada producto con `comprado == 1`,
     `quote_ready`/`awaiting_consent` reflejados en sus etapas, corte
     `declarado.compradas == 5`.
   - **Fila corrupta**: insertar un `ConversationRecord` con `data` inválido → el
     endpoint responde 200 y la fila corrupta simplemente no cuenta.
   - **Los 5 productos siempre**: con una sola venta de hogar, los otros 4 aparecen
     con ceros (criterio "se distingue cuáles no se compraron").
   - Las rutas existentes del panel siguen intactas (smoke de `GET /panel/cohortes`).

**Pruebas / verificación**: `.venv\Scripts\python.exe -m pytest -q` en verde;
manual: `uvicorn` + `curl http://localhost:8000/api/v1/panel/metricas` con el seed
cargado.
**Riesgos**: documentos viejos en Postgres local con shapes previos a A4/B5 — cubierto
por el `try/except` por fila; volumen (cientos de filas máx. en demo) hace válido el
cálculo en Python sin SQL por JSON (portable a SQLite, sin acoplarse a JSONB).

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `feat(panel): add funnel metrics endpoint by product`

---

## Fase 2 — Sección "Funnel de ventas" en el panel

**Proyecto**: frontend
**Objetivo**: el panel muestra el funnel legible de un vistazo, sobrio (CSS puro),
sin dejar de mostrar lo proactivo de G3.
**Archivos afectados**:
- [frontend/src/shared/services/api.js](frontend/src/shared/services/api.js)
  → `getPanelMetricas()`
- `frontend/src/features/panel/composables/` → nuevo `useFunnel.js`
- `frontend/src/features/panel/components/` → nuevos `FunnelSection.vue` y
  `FunnelProductRow.vue`
- [frontend/src/features/panel/PanelView.vue](frontend/src/features/panel/PanelView.vue)
  → monta la sección (sin tocar la lógica de cohortes)

**Impacto en contrato API (front↔back)**: No — consume el endpoint creado en Fase 1,
sin cambios de backend ni env vars (usa `VITE_API_URL` vía el cliente base).
**Acciones**:
1. `getPanelMetricas()` en `api.js`: `api.get('/api/v1/panel/metricas')` (patrón de
   `getPanelCohortes`).
2. `useFunnel.js`: estado `metricas/isLoading/error` + `reintentar()` — calco del
   patrón de [usePanel.js:20-36](frontend/src/features/panel/composables/usePanel.js#L20-L36)
   (API caída → mensaje + botón reintentar, jamás pantalla rota).
3. `FunnelSection.vue`: 3–4 tiles arriba (conversaciones, compradas, conversión
   global, corte afiliado vs declarado) + una fila por producto.
4. `FunnelProductRow.vue`: nombre del producto + 4 barras horizontales
   (recomendado → cotizado → consentimiento → comprado) con ancho proporcional al
   máximo de la etapa inicial (CSS `width: %`, colores del tema del chat,
   `--chat-green*`), conteo y tasa entre etapas; producto en cero → fila atenuada
   "sin ventas" (se ve, no desaparece).
5. Montar `<FunnelSection />` en `PanelView.vue` debajo del header y antes de las
   cohortes, con subtítulo tipo "Funnel de ventas por producto"; si
   `fuente === "sin_datos"`, banner sugiriendo correr el seed (mismo tono del banner
   existente [PanelView.vue:31-33](frontend/src/features/panel/PanelView.vue#L31-L33)).
6. Sobriedad: sin librerías, sin animaciones, tipografía y espaciado de la vista
   actual — es evidencia de gestión, no el show.

**Pruebas / verificación**: `npm run build` OK; manual: `python dev.py`, sembrar con
`seed_demo --replace`, abrir `/panel` → tiles y 5 productos con datos, ninguna
sección vacía; matar el backend y recargar → mensaje de error + reintentar (no
pantalla rota); `GET /panel/cohortes` sigue pintando cohortes intacto.
**Riesgos**: sobrecargar la vista (la advertencia de la dueña del reto) — mitigado:
una sección compacta, colapsable visualmente por jerarquía tipográfica, cohortes
siguen primero en el pitch del proactivo.

🛑 **CHECKPOINT final** — G5 completa. Recordar: anotar en el vault la brecha de G1
(solicitudes/detalle/atípicos siguen pendientes) y marcar los criterios de G5.
**Commit sugerido**: `feat(front): sales funnel dashboard in panel view`
