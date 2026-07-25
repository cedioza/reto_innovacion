# Plan — E2: Página de la aseguradora simulada · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-25 · **Tipo**: plan de implementación por fases.
> **Base**: [20260725-e1-handoff-correo-aseguradora-simulada.plan.md](.claude/analysis/plans/20260725-e1-handoff-correo-aseguradora-simulada.plan.md)
> (E1, ya mergeado a master: el correo de comprobante ya envía el link
> `{FRONTEND_URL}/aseguradora/{token}` y toda solicitud tiene `handoff_token` e
> `insurer_name`) y
> [20260725-d3-tarjetas-recomendacion-cotizacion-comparador.plan.md](.claude/analysis/plans/20260725-d3-tarjetas-recomendacion-cotizacion-comparador.plan.md)
> (patrón de tarjetas/estética del front).
> Tarea del vault: `07 - Tareas/Feature E - Cierre automatico/E2 - Pagina de la aseguradora simulada.md`
> (depende de E1 ✅; no bloquea a nadie). Nota: el criterio "estado visible en el
> panel" apunta a G2, que aún no existe — este plan deja el estado listo para que G2
> lo lea.
> **Proyectos afectados**: ambos (backend primero: los 2 endpoints del handoff; luego
> la página Vue que los consume).
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

El link del correo de E1 abre una página de "aseguradora" (`/aseguradora/{token}`,
ruta del mismo front): resumen de la póliza pre-aprobada + botón "Continuar al pago"
→ pantalla de éxito **"Tu póliza quedó activa (simulación)"**, marcando la solicitud
como `finalizada_demo`. Cierra el arco "ya quedé asegurado" que el jurado recorre
solo, **sin sesión del chat** (incógnito) y **sin un solo campo de pago**.

Criterios de aceptación del vault:
1. El link del correo funciona en incógnito (sin sesión del chat).
2. Cero campos de datos de pago, ni siquiera decorativos.
3. El estado `finalizada_demo` queda registrado (G2 lo mostrará en el panel).

## Contexto / hallazgos del análisis

**Lo que E1 ya dejó listo:**

- El correo ya apunta a `{settings.frontend_url}/aseguradora/{token}`
  ([handoff.py:59](backend/app/services/handoff.py#L59)) — la URL de esta página es
  contrato existente, no se inventa aquí.
- Toda `ConsentedApplication` trae `handoff_token` (43 chars URL-safe),
  `insurer_name` y `email` ([conversation.py schemas](backend/app/schemas/conversation.py)).

**🚨 Hallazgo de arquitectura (el hueco real de esta tarea):**

- [applications.py:12-13](backend/app/repositories/applications.py#L12-L13) — el
  repositorio de solicitudes es un dict **de instancia**, y
  [agent_tools.py](backend/app/services/agent_tools.py) crea `ConsentService()`
  **nuevo en cada `cerrar_venta`** → la solicitud del camino del chat solo sobrevive
  embebida en `session.application`; nadie puede buscarla después por token. El
  endpoint estructurado sí usa el singleton compartido (`conversation_service._consent`).
- Resolución: **singleton de módulo `consent_service`** en
  [consent.py](backend/app/services/consent.py) (mismo patrón que
  [conversation.py:185](backend/app/services/conversation.py#L185)), consumido por
  `agent_tools`, `ConversationService` y el router nuevo de handoff. Así TODAS las
  solicitudes viven en el mismo repositorio y el token siempre resuelve.
- `ApplicationRepository` gana `find_by_token(token)` (itera los values — son
  puñados; C3 lo volverá query cuando llegue Postgres).

**Estado `finalizada_demo`:**

- `ConversationState` ([conversation.py:7-12](backend/app/schemas/conversation.py#L7-L12))
  termina en `READY_FOR_PAYMENT`. Se agrega `FINALIZED_DEMO = "finalizada_demo"`
  (aditivo: los checks existentes son por igualdad/membresía, ningún match exhaustivo
  se rompe). El clic en "Continuar al pago" pone `application.state = finalizada_demo`
  — **idempotente**: el segundo clic (o un F5 del jurado) devuelve 200 con el mismo
  estado, jamás error.

**Privacidad del endpoint público** (el link lo abre el jurado, sin auth):

- La respuesta del handoff es **sanitizada**: producto, aseguradora, primas,
  coberturas, exclusiones, estado y fecha de consentimiento. **NUNCA** `email`, ni
  `profile`, ni `session_id` (un token filtrado no debe exponer datos del cliente).

**Frontend:**

- [router/index.js](frontend/src/router/index.js) — solo `/` y `/panel`; se agrega
  `/aseguradora/:token`. La página **no usa localStorage ni sesión** (criterio 1:
  incógnito) — todo sale del token de la URL.
- [api.js](frontend/src/shared/services/api.js) — patrón listo para `getHandoff()` y
  `finalizeHandoff()`; los errores traen `.status` (distinguir 404 = link
  inválido/solicitud perdida vs. API caída).
- Feature nueva autocontenida `frontend/src/features/aseguradora/` (regla del front:
  carpeta + ruta; no importa de otras features).
- ⚠️ Nota de deploy ya conocida (H1): la ruta directa `/aseguradora/x` en el deploy
  estático de Dokploy necesita el fallback de SPA (history mode) — pendiente
  operativo de H1, no de este plan (en dev, Vite lo maneja solo).

**Decisiones resueltas en el análisis:**

1. Rutas: `GET /api/v1/handoff/{token}` (consulta) y
   `POST /api/v1/handoff/{token}/finalize` (clic del botón). Router nuevo
   `handoff.py` con prefijo `/handoff` colgado del router raíz `/api/v1`.
2. El router delega en el **singleton `consent_service`** (get por token +
   finalize); sin service nuevo — el dueño del repositorio de solicitudes es
   ConsentService y el handoff es una operación sobre solicitudes.
3. Branding: página con el `insurer_name` de la solicitud + banner fijo
   "Entorno de demostración — aquí entraría la pasarela real de la aseguradora"
   (criterio 2 y nota del vault: etiqueta visible, cero campos de pago).
4. Backend reiniciado (solicitudes en memoria, C3 pendiente): el `GET` devuelve 404
   y la página muestra "No encontramos tu solicitud — puede haber expirado; vuelve
   al chat para retomarla" con link a `/`. Degradación honesta, sin pantalla rota.

## Decisiones pendientes (bloqueantes)

(ninguna)

## Principios

- Backend primero (endpoints), frontend después (página que los consume).
- Endpoint público = respuesta sanitizada (nunca email/perfil/session_id).
- Aditivo: enum, campos y rutas nuevas; nada existente cambia de shape.
- Finalize idempotente: el jurado puede refrescar y re-clicar sin romper nada.
- Verde por fase (pytest / build); TDD-light en fases backend; rutas negativas
  (404 token desconocido, 422/405 donde aplique) sin 500.
- Cero dependencias nuevas, cero env vars nuevas (la URL ya usa `FRONTEND_URL`).

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | ambos | Ninguno | 5m | _(sin commit)_ |
| 1 | Singleton de consentimiento + `GET /handoff/{token}` | backend | Medio (ruta nueva + refactor interno) | 30m | `feat(back): add handoff lookup endpoint by token` |
| 2 | `POST /handoff/{token}/finalize` + estado `finalizada_demo` | backend | Medio (ruta nueva) | 20m | `feat(back): finalize handoff with demo state` |
| 3 | Página `/aseguradora/{token}` en el front | frontend | Alto (fin del recorrido del jurado) | 35m | `feat(front): add simulated insurer page` |

Total: ~90m.

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: ambos
**Objetivo**: punto de partida verde.
**Archivos afectados**: ninguno.
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Backend desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` → línea base
   esperada **269 passed + 9 skipped** (master con B1+E1 integrados).
2. Frontend desde `frontend/`: `npm run build` → OK.
3. Confirmar con `git log` que master contiene E1 (`ab02979`) — prerequisito duro.

**Pruebas / verificación**: las de arriba.
**Riesgos**: ninguno.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit)_

---

## Fase 1 — Singleton de consentimiento + `GET /api/v1/handoff/{token}`

**Proyecto**: backend
**Objetivo**: cualquier solicitud (venga del chat o del endpoint estructurado) es
resoluble por su token, con respuesta pública sanitizada.
**Archivos afectados**:
- [repositories/applications.py](backend/app/repositories/applications.py) —
  `find_by_token(token) -> Any | None` (itera values comparando
  `application.handoff_token`).
- [services/consent.py](backend/app/services/consent.py) — singleton de módulo
  `consent_service = ConsentService()` al final (patrón `conversation_service`);
  método nuevo `get_application_by_token(token)`.
- [services/agent_tools.py](backend/app/services/agent_tools.py) — `_cerrar_venta`
  usa `consent_service` (el singleton) en vez de `ConsentService()` por llamada.
- [services/conversation.py](backend/app/services/conversation.py) —
  `self._consent = consent_service` (comparte el mismo repositorio).
- [schemas/handoff.py](backend/app/schemas) (nuevo) — `HandoffSummary`: `product_id`,
  `product_name`, `insurer_name`, `monthly_premium`, `annual_premium`, `currency`,
  `coverage_details`, `exclusions`, `state`, `consent_timestamp`. SIN email/perfil/
  session_id.
- [api/routes/handoff.py](backend/app/api/routes) (nuevo) — router prefijo
  `/handoff`, `GET /{token}` → 200 `HandoffSummary` / 404 token desconocido;
  registrado en [main.py](backend/app/main.py) bajo `api_v1`.
- Tests nuevos (`tests/test_handoff_endpoint.py`): cierre por tool guionizada (sin
  LLM real) → GET con ese token → 200 con los campos sanitizados y las cifras
  exactas del motor; cierre por `POST /consent` → GET con su token → 200 (ambos
  caminos comparten repositorio — el test que fija el singleton); GET token
  inventado → 404; la respuesta NO contiene `email` ni `profile` (aserción
  explícita de privacidad).

**Impacto en contrato API (front↔back)**: **Sí — aditivo.** Ruta nueva
`GET /api/v1/handoff/{token}`. **Quién consume**: Fase 3 (front, este plan) y el
correo de E1 (ya enlaza a la página que la usará).
**Acciones**:
1. TDD-light: tests primero (rojo: ruta inexistente / lookup inexistente).
2. Refactor a singleton + repo + schema + router.
3. Suite completa verde (los tests de E1 sobre `capture` siguen intactos).

**Pruebas / verificación**: pytest verde (269 + nuevos); manual: uvicorn + flujo
sembrado por endpoints (`/profile` → `/accept` → `/consent` con email dummy) → GET
`/api/v1/handoff/{token de la respuesta}` → 200 sanitizado; token falso → 404.
**Riesgos**: el refactor al singleton toca el camino de `cerrar_venta` — la suite de
E1 (test_handoff_flow) es la red de seguridad; los tests que hoy espían
`ConsentService.capture` siguen funcionando (el singleton es una instancia de la
misma clase).

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `feat(back): add handoff lookup endpoint by token`

---

## Fase 2 — `POST /api/v1/handoff/{token}/finalize` + estado `finalizada_demo`

**Proyecto**: backend
**Objetivo**: el clic en "Continuar al pago" deja la solicitud en `finalizada_demo`,
de forma idempotente, lista para que G2 la muestre en el panel.
**Archivos afectados**:
- [schemas/conversation.py](backend/app/schemas/conversation.py) —
  `ConversationState` += `FINALIZED_DEMO = "finalizada_demo"` (aditivo).
- [services/consent.py](backend/app/services/consent.py) — método
  `finalize_by_token(token)`: no existe → `ValueError` (→404); existe →
  `application.state = FINALIZED_DEMO`, re-persistir, devolver la application
  (idempotente: si ya estaba finalizada, devolverla igual con 200).
- [api/routes/handoff.py](backend/app/api/routes/handoff.py) — `POST /{token}/finalize`
  → 200 `HandoffSummary` (con `state: finalizada_demo`) / 404.
- Tests (mismo archivo de la Fase 1): finalize feliz → 200 y estado nuevo; segundo
  finalize → 200 idéntico (idempotencia); GET posterior refleja `finalizada_demo`;
  token desconocido → 404; los estados previos del funnel no cambian (la sesión de
  conversación NO se toca — solo la solicitud).

**Impacto en contrato API (front↔back)**: **Sí — aditivo.** Ruta nueva + valor nuevo
de enum en `state` (los consumidores actuales del enum no filtran por él). **Quién
consume**: Fase 3 (front) y G2 (panel, futuro).
**Acciones**:
1. TDD-light: tests primero.
2. Enum + service + ruta.
3. Suite completa verde.

**Pruebas / verificación**: pytest verde; manual: flujo sembrado → finalize por curl
→ 200 `finalizada_demo` → repetir → 200 igual; token falso → 404.
**Riesgos**: mínimos (aditivo puro sobre la Fase 1).

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 3 sin aprobación del usuario.
**Commit sugerido**: `feat(back): finalize handoff with demo state`

---

## Fase 3 — Página `/aseguradora/{token}` en el front

**Proyecto**: frontend
**Objetivo**: el final del recorrido del jurado: abrir el link del correo → ver la
póliza pre-aprobada → "Continuar al pago" → "Tu póliza quedó activa (simulación)".
**Archivos afectados**:
- [api.js](frontend/src/shared/services/api.js) — `getHandoff(token)` →
  `GET /api/v1/handoff/{token}`; `finalizeHandoff(token)` →
  `POST /api/v1/handoff/{token}/finalize`.
- `frontend/src/features/aseguradora/InsurerView.vue` (nuevo) — página
  autocontenida:
  - encabezado con `insurer_name` (branding genérico sobrio, variables de
    `chat-theme.css` o propias) + **banner fijo** "Entorno de demostración — aquí
    entraría la pasarela real de la aseguradora";
  - resumen de póliza: producto, prima mensual grande (formato es-CO) y anual,
    coberturas, exclusiones (colapsables como en `QuoteCard`);
  - botón **"Continuar al pago"** (sin un solo campo de pago) → `finalizeHandoff` →
    pantalla de éxito "🎉 Tu póliza quedó activa (simulación)" (y si `state` ya
    viene `finalizada_demo` en el GET inicial, mostrar directamente el éxito —
    consistente con la idempotencia);
  - estados de error: 404 → "No encontramos tu solicitud — puede haber expirado;
    vuelve al chat para retomarla" + link a `/`; API caída/timeout → mensaje amable
    con reintento manual; spinner de carga inicial.
  - **Cero uso de localStorage/sesión** — todo desde el token de la URL (incógnito).
- [router/index.js](frontend/src/router/index.js) — ruta
  `{ path: '/aseguradora/:token', name: 'aseguradora', component: InsurerView }`.

**Impacto en contrato API (front↔back)**: No cambia el contrato (consume las rutas
de las Fases 1-2).
**Acciones**:
1. Funciones en `api.js`.
2. Feature + ruta.
3. `npm run build` OK.

**Pruebas / verificación**: `npm run build`; manual e2e SIN LLM: sembrar solicitud
por endpoints (con email dummy o el buzón real si quieres ver el correo), copiar el
`handoff_token` de la respuesta y abrir `http://localhost:5173/aseguradora/<token>`
**en ventana de incógnito** (criterio 1) → resumen correcto → clic → éxito → F5 →
sigue en éxito (idempotencia); token inventado → mensaje de "no encontramos tu
solicitud"; backend caído → mensaje amable. Verificación visual en ancho móvil.
**Riesgos**: el fallback de SPA en el deploy estático (H1) — en dev funciona; anotar
para el checklist de despliegue; gusto visual (es la última pantalla que ve el
jurado — sobria, sin parecer "generada sin criterio").

🛑 **CHECKPOINT** — fin del plan.
**Commit sugerido**: `feat(front): add simulated insurer page`

---

## Deuda / fuera de alcance (anotada para el vault)

- **G2 (panel)**: leerá las solicitudes `finalizada_demo` — el estado ya queda
  persistido y consultable; G1/G2 definirán el endpoint de listado.
- **C3 (Postgres)**: los tokens sobreviven redeploys cuando las solicitudes pasen a
  BD; `find_by_token` se vuelve query. Hasta entonces, un redeploy invalida los
  links viejos (la página degrada con el mensaje de "expirado").
- **H1**: fallback de SPA para rutas directas (`/aseguradora/x`, `/panel`) en el
  deploy estático de Dokploy — pendiente operativo ya conocido.
- **E3/E4**: el PDF adjunto y la confirmación por WhatsApp se enganchan en el mismo
  flujo de cierre; el token/página ya los soportan sin cambios.
