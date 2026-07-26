# Plan — G3: Disparador proactivo con la base real · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-25 · **Tipo**: plan de implementación por fases.
> **Base**: [20260725-c2-base-afiliados-postgres.plan.md](.claude/analysis/plans/20260725-c2-base-afiliados-postgres.plan.md)
> (tabla `afiliados` real + sintéticos `sint_*`, mergeado hoy),
> [20260725-b3-propension-multicategoria-explicable.plan.md](.claude/analysis/plans/20260725-b3-propension-multicategoria-explicable.plan.md)
> (motor de propensión explicable multicategoría),
> [20260725-a3-orquestador-conversacional-llm.plan.md](.claude/analysis/plans/20260725-a3-orquestador-conversacional-llm.plan.md)
> (conversación libre por `/message`). Tarea del brain: **G3 — Disparador proactivo
> con la base real** (Feature G; depende de C2 ✔ y A3 ✔).
> **Proyectos afectados**: ambos (backend primero, frontend consume).
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

El componente proactivo demostrable en <20s: `GET /api/v1/panel/cohortes` devuelve
2-3 cohortes predefinidas con **conteo real desde Postgres** sobre la tabla
`afiliados`, cada una con el producto que el motor de propensión recomienda y por
qué; desde el panel se elige un afiliado de la muestra y "Simular oferta proactiva"
abre una conversación **iniciada por el sistema** donde el agente ya conoce el perfil
y arranca con la oferta justificada (transparencia del porqué del contacto). "El
seguro correcto, en el momento correcto, por el canal correcto" — canal web simulado
(el disparo batch/WhatsApp real queda como deuda documentada, según la tarea).

## Contexto / hallazgos del análisis

**Lo que ya existe y este plan solo compone:**

- **Base real consultable**: [AffiliateRecord](backend/app/models/affiliate_record.py)
  (tabla `afiliados`, C2) tiene TODO lo necesario para cohortes: `age_range`,
  `household_segment`, `population_segment`, las 5 marcas de consumo
  (`uses_drogueria`, `uses_vivienda`, …) y los sintéticos marcados
  (`sint_tiene_vehiculo`, `sint_tiene_credito`, `sint_tiene_hijos`). El repo
  [affiliates.py](backend/app/repositories/affiliates.py) consulta la BD con
  fallback CSV, pero **solo tiene `find/exists/count`** — faltan los queries de
  cohorte (conteo + muestra por filtros).
- **Perfil precargado al crear conversación**:
  [conversation.py:47-75](backend/app/services/conversation.py#L47-L75) —
  `create(ConversationCreate(document_number=SERIE))` ya resuelve el afiliado real y
  precarga `ProfileData` (incluye `has_children/has_vehicle/has_credit` post-B3). El
  disparo proactivo es exactamente este camino + mensaje de apertura.
- **Recomendación explicable**: `PropensityService.evaluate(profile)`
  ([propensity.py:274-334](backend/app/services/propensity.py#L274)) devuelve
  producto + `reasons` multicategoría (B3) — sirve para el "producto de la cohorte"
  y para la oferta del elegido.
- **Tarjeta de recomendación que el chat ya pinta**: shape en
  [orchestrator.py:457-473](backend/app/services/orchestrator.py#L457-L473) —
  mensaje `type="recommendation"` con payload `{product_id, product_name, reasons}`.
  El disparo puede emitir la misma tarjeta y
  [RecommendationCard.vue](frontend/src/features/chat/components/RecommendationCard.vue)
  la renderiza sin tocar el frontend del chat.
- **El chat se rehidrata por localStorage**:
  [useChat.js:44-81](frontend/src/features/chat/composables/useChat.js#L44-L81) lee
  `chat_session_id` y reconstruye la conversación por `GET /conversations/{id}` —
  el panel solo necesita setear ese valor y navegar a `/`.
- **Panel**: [PanelView.vue](frontend/src/features/panel/PanelView.vue) es un
  placeholder (G1/G2 pendientes) con ruta `/panel` ya registrada en
  [router/index.js](frontend/src/router/index.js). Este plan construye la sección
  proactiva; ventas/transcripciones siguen siendo G1/G2.
- **Backend sin router de panel**: `api/routes/` no tiene `panel.py` — endpoint
  nuevo, registrado en [main.py](backend/app/main.py) bajo `/api/v1`.
- Regla de capas: el router llama a un service; **cada service posee UN repo** — los
  queries de cohorte viven en `AffiliateRepository`, expuestos vía
  `AffiliateService`, y un `ProactiveService` compone `AffiliateService` +
  `PropensityService` + `conversation_service` (patrón orquestador permitido).

**Valores reales de los buckets**: `age_range` se canonicaliza por dígitos
(`"18-25"`, `"26-35"`, …) y las marcas son booleanos — pero los valores exactos de
`household_segment`/`population_segment` en el dataset real deben confirmarse
consultando la BD en la Fase 1 (los filtros de las cohortes se definen contra
valores reales, no adivinados).

**Cuota Gemini**: el disparo NO gasta LLM — el mensaje de apertura es plantilla
determinista por código (transparencia del contacto + señal de la cohorte + producto
con razones del motor). El LLM entra solo cuando el usuario responde (camino
`/message` existente). Con las keys free tier (20 req/día) esto importa para la demo.

## Decisiones pendientes (bloqueantes)

(ninguna — resueltas en el análisis:)

- **Canal del disparo**: web simulado (crear conversación + navegar al chat). El
  envío real por WhatsApp queda como deuda documentada en el propio plan y el README
  del backend (la tarea lo permite explícitamente).
- **Cohortes predefinidas en código** (constantes del service, 3): filtros sobre
  columnas reales + producto esperado; los valores exactos de los filtros se fijan
  en la Fase 1 leyendo la BD real. Borrador: (a) jóvenes 18-35 con
  `uses_drogueria=True` y segmento familiar → vida/accidentes; (b)
  `uses_vivienda=True` → hogar; (c) `sint_tiene_vehiculo=True` → movilidad.
- **El estado de la conversación disparada** queda en `collecting_profile` con
  perfil y recomendación precargados + tarjeta de recomendación — el flujo normal
  (cotizar → consentir) sigue el camino ya existente, sin estados nuevos.
- **Sin BD** (DATABASE_URL vacía → SQLite local sin datos): los conteos devuelven 0
  y el panel lo muestra con un aviso — nunca 500. El conteo "real desde Postgres"
  del criterio se demuestra con la BD local cargada (`cargar_afiliados.py` de C2) o
  la de Dokploy.

## Principios

- Verde por fase: `.venv\Scripts\python.exe -m pytest -q` (backend) / `npm run build`
  (frontend); ambos servidores levantan.
- **Backend primero** (Fases 1-2), frontend consume lo que ya existe (Fase 3).
- Contrato HTTP explícito y aditivo: endpoints nuevos bajo `/api/v1/panel/*`; nada
  existente cambia.
- Cero dependencias nuevas; cero env vars nuevas; cero gasto de LLM en el disparo.
- Los datos sintéticos se presentan como tales (etiqueta `sint_` ya existente — la
  transparencia es parte del pitch).

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | ambos | Ninguno | 10m | _(sin commit)_ |
| 1 | Queries de cohorte + `GET /panel/cohortes` | backend | Aditivo | 35m | `feat(panel): add cohort endpoint over real affiliate base` |
| 2 | Disparo proactivo `POST /panel/cohortes/{id}/disparar` | backend | Aditivo | 30m | `feat(panel): add proactive offer trigger endpoint` |
| 3 | Panel proactivo en el frontend | frontend | Aditivo | 35m | `feat(front): proactive panel with cohort trigger to chat` |

Total estimado: ~110m (estimación del brain: 3h — dentro de rango).

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: ambos
**Objetivo**: baseline verde y valores reales del dataset para definir cohortes.
**Archivos afectados**: ninguno (solo lectura).
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Backend: `.venv\Scripts\python.exe -m pytest -q` (esperado: 424 passed, 9 skipped).
   Frontend: `npm run build` OK.
2. Con la BD local arriba (`docker compose up -d db`): consultar valores DISTINCT
   reales de `age_range`, `household_segment`, `population_segment` y conteos de las
   marcas (`uses_drogueria`, `uses_vivienda`, `sint_tiene_vehiculo`) en la tabla
   `afiliados` — si está vacía, correr primero `cargar_afiliados.py` (C2). Anotar
   los valores para los filtros de la Fase 1.
3. Confirmar el shape del payload `recommendation` que consume
   `RecommendationCard.vue` (claves `product_id/product_name/reasons`).
**Pruebas / verificación**: suite y build en verde; lista de valores reales anotada.
**Riesgos**: tabla `afiliados` vacía en local → cargarla es prerequisito de la demo,
no de la implementación (los tests usan datos sembrados propios).

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit — fase de solo lectura)_

---

## Fase 1 — Queries de cohorte + `GET /panel/cohortes`

**Proyecto**: backend
**Objetivo**: el conteo real desde Postgres por cohorte, con producto recomendado y
porqué, expuesto en un endpoint que el panel pueda pintar (criterio 1 de G3).
**Archivos afectados**:
[affiliates.py (repo)](backend/app/repositories/affiliates.py) ·
[affiliate.py (service)](backend/app/services/affiliate.py) ·
`backend/app/services/proactive.py` (nuevo) ·
`backend/app/api/routes/panel.py` (nuevo) ·
`backend/app/schemas/panel.py` (nuevo) ·
[main.py](backend/app/main.py) ·
`backend/tests/test_panel_cohorts.py` (nuevo)
**Impacto en contrato API (front↔back)**: **Sí (aditivo)** — endpoint nuevo
`GET /api/v1/panel/cohortes` → `{cohortes: [{id, nombre, descripcion, criterio_humano,
total, muestra: [{serie, age_range, household_segment, señales}], producto:
{product_id, product_name}, razones: [...]}], fuente: "postgres"|"sin_datos"}`.
El frontend lo consume en la **Fase 3**.
**Acciones**:
1. Repo: `count_by_filters(filters) -> int` y `sample_by_filters(filters, limit=5)
   -> list[AffiliateRecord]` sobre la tabla `afiliados` (SQLModel `select` +
   `func.count`, filtros como igualdades/`IN` sobre columnas del modelo — sin SQL
   crudo). Sin BD o tabla vacía → 0 / lista vacía (mismo patrón de fallback benigno
   que el resto del repo, sin excepción).
2. Service: definir las 3 cohortes como constantes (id, nombre, descripción,
   `criterio_humano` para el panel, filtros para el repo) usando los valores REALES
   anotados en la Fase 0. `ProactiveService.list_cohorts()`: por cohorte, conteo +
   muestra (vía `AffiliateService`, que expone los métodos nuevos de su repo) +
   recomendación del motor (`PropensityService.evaluate` sobre el perfil del primer
   miembro de la muestra) con sus `reasons`.
3. Router `panel.py` (prefijo `/panel`, sin lógica) + registro en `main.py` +
   schemas Pydantic en `schemas/panel.py` (nunca exponer el modelo SQLModel).
4. Tests (TDD-light): con engine sembrado (fixture con afiliados de prueba en las 3
   cohortes) — conteos correctos, muestra ≤5, producto y razones presentes; BD sin
   filas → `total: 0` y `fuente: "sin_datos"`, status 200 (nunca 500). Ruta
   negativa: `GET /api/v1/panel/cohortes/inexistente` no existe todavía (llega en
   Fase 2 el subrecurso) — verificar 404 de FastAPI por defecto.
**Pruebas / verificación**: pytest verde; manual: con BD local cargada,
`curl /api/v1/panel/cohortes` muestra conteos reales (p. ej. "4.312 afiliados").
**Riesgos**: rendimiento del `count` sobre 500k filas — aceptable en Postgres local
(índice PK + columnas simples); si la demo lo necesitara, cachear en memoria del
proceso es un follow-up, no parte de esta fase.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `feat(panel): add cohort endpoint over real affiliate base`

---

## Fase 2 — Disparo proactivo `POST /panel/cohortes/{id}/disparar`

**Proyecto**: backend
**Objetivo**: el disparo abre una conversación iniciada por el sistema donde el
agente ya conoce el perfil y arranca con la oferta justificada (criterio 2 de G3).
**Archivos afectados**:
`backend/app/services/proactive.py` ·
`backend/app/api/routes/panel.py` ·
`backend/app/schemas/panel.py` ·
`backend/tests/test_panel_trigger.py` (nuevo)
**Impacto en contrato API (front↔back)**: **Sí (aditivo)** — endpoint nuevo
`POST /api/v1/panel/cohortes/{cohorte_id}/disparar` body `{serie}` → 201
`{session_id, serie, producto: {...}, mensaje_apertura}`. Errores: cohorte
desconocida → 404; serie inexistente en la base → 404; body inválido → 422.
El frontend lo consume en la **Fase 3**.
**Acciones**:
1. `ProactiveService.trigger(cohorte_id, serie)`:
   - valida cohorte y afiliado (`AffiliateService.lookup`);
   - crea la conversación por el camino existente
     `conversation_service.create(ConversationCreate(document_number=serie))` —
     perfil real precargado;
   - corre `PropensityService.evaluate` y setea `session.recommendation`;
   - agrega DOS mensajes assistant deterministas (cero LLM): (a) apertura con la
     transparencia del contacto — quién lo contacta, por qué (criterio humano de la
     cohorte + señal concreta del perfil) y la oferta del momento de vida; (b) la
     tarjeta `type="recommendation"` con el payload exacto de
     [orchestrator.py:462-473](backend/app/services/orchestrator.py#L462-L473) para
     que el chat la pinte;
   - `next_action` acorde ("Respondé para cotizar en 2 minutos") y save (persistido
     en Postgres por C3 — sobrevive reinicios).
2. Router: `POST /panel/cohortes/{id}/disparar` delgado → service; mapear
   `ValueError` a 404/400 como en los routers existentes.
3. Tests (TDD-light): disparo feliz (201, sesión consultable por
   `GET /conversations/{id}` con perfil + recomendación + 2 mensajes con timestamp);
   el porqué de la cohorte aparece en el mensaje de apertura; cohorte inexistente →
   404; serie inexistente → 404; body sin `serie` → 422 — nunca 500.
4. Documentar la deuda (batch/WhatsApp real) en el README del backend, sección
   panel/proactivo.
**Pruebas / verificación**: pytest verde; manual: `curl -X POST .../disparar` y
`GET /conversations/{session_id}` muestra la conversación abierta por el sistema.
**Riesgos**: el flujo posterior (usuario responde) entra por `/message` (LLM) — ya
existente y fuera del alcance; si la sesión disparada rompiera alguna expectativa
del orquestador (p. ej. historial que arranca con assistant), el test e2e de esta
fase lo detecta con el LLM mockeado como en `test_e2e_orchestrator.py`.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 3 sin aprobación del usuario.
**Commit sugerido**: `feat(panel): add proactive offer trigger endpoint`

---

## Fase 3 — Panel proactivo en el frontend

**Proyecto**: frontend
**Objetivo**: el recorrido demo de <20 segundos (criterio 3): abrir `/panel`, ver
cohortes con conteo real, elegir un perfil, disparar, y caer en el chat con la
conversación proactiva ya abierta.
**Archivos afectados**:
[PanelView.vue](frontend/src/features/panel/PanelView.vue) (deja de ser placeholder) ·
`frontend/src/features/panel/components/CohortCard.vue` (nuevo) ·
`frontend/src/features/panel/composables/usePanel.js` (nuevo) ·
[api.js](frontend/src/shared/services/api.js)
**Impacto en contrato API (front↔back)**: No (consume los endpoints de Fases 1-2).
**Acciones**:
1. `api.js`: `getPanelCohortes()` y `dispararOferta(cohorteId, serie)` (mismo patrón
   de funciones exportadas existente).
2. `usePanel.js`: estado (cohortes, cargando, error, disparando), carga al montar,
   y `disparar(cohorteId, serie)` que al recibir `session_id` setea
   `localStorage.chat_session_id` y navega a `/` — el chat se rehidrata solo
   ([useChat.js:44-81](frontend/src/features/chat/composables/useChat.js#L44-L81)).
3. `PanelView.vue` + `CohortCard.vue`: por cohorte — nombre, criterio humano,
   **conteo real** destacado ("4.312 afiliados con este perfil"), producto
   recomendado con razones, muestra de afiliados (serie + atributos + señal) con
   selección, y botón "Simular oferta proactiva". Estados: cargando, `fuente:
   "sin_datos"` (aviso de BD vacía), error de API (mensaje, no pantalla rota).
   Estilo consistente con el resto (clases y layout del chat/aseguradora).
4. Caso API caída: mensaje de error con botón reintentar.
**Pruebas / verificación**: `npm run build` OK; manual del recorrido completo:
`/panel` → cohorte → elegir perfil → disparar → chat con apertura justificada +
tarjeta de recomendación → responder un mensaje (ya con LLM) sigue el flujo normal.
Cronometrar que el recorrido cabe en <20s.
**Riesgos**: si hay una conversación previa en `chat_session_id`, el disparo la
reemplaza — aceptable para la demo (el localStorage es del navegador del demo); se
anota en el README del frontend si genera fricción.

🛑 **CHECKPOINT FINAL** — G3 cumple sus 3 criterios: conteo real desde Postgres,
disparo que abre conversación con perfil conocido y oferta justificada, y recorrido
demo <20s. Marcar G3 en el brain (y anotar la deuda batch/WhatsApp).
**Commit sugerido**: `feat(front): proactive panel with cohort trigger to chat`
