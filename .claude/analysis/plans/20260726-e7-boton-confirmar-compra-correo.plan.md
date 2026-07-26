# Plan — E7: Botón de confirmar compra en el correo (bug) · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-26 · **Tipo**: plan de implementación por fases (bugfix).
> **Base**: [20260725-e1-handoff-correo-aseguradora-simulada.plan.md](.claude/analysis/plans/20260725-e1-handoff-correo-aseguradora-simulada.plan.md)
> (el correo con el botón lo construyó E1) y
> [20260725-e2-pagina-aseguradora-simulada.plan.md](.claude/analysis/plans/20260725-e2-pagina-aseguradora-simulada.plan.md)
> (la página `/aseguradora/{token}` y la pantalla de éxito ya existen y están probadas).
> Tarea del vault: `07 - Tareas/Feature E - Cierre automatico/E7 - Boton de confirmar compra en el correo.md`
> (depende de E1 y E2 — ambas hechas; **bloquea H8**, la grabación del demo).
> **Proyectos afectados**: backend (código); producción (configuración en Dokploy, fuera del repo).
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

El botón "Confirmar y finalizar con {aseguradora}" del correo de comprobante debe
abrir `/aseguradora/{token}` **en producción** (`https://colsubsidio.zyvra.lat`),
desde incógnito y desde el teléfono, y tras "Continuar al pago" mostrar **"Tu póliza
quedó activa (simulación)"** con la solicitud en `finalizada_demo`. Además, dejar un
**test que fije la causa raíz** para que el bug no reaparezca en el siguiente deploy:
el correo nunca sale con un link a `localhost` desde un backend desplegado.

## Contexto / hallazgos del análisis

**Cómo se arma el botón hoy (cadena completa, todo ya existe):**

- [handoff.py:63](backend/app/services/handoff.py#L63) — `build_handoff_email` arma
  `handoff_url = f"{settings.frontend_url}/aseguradora/{token}"`. El botón
  ([handoff.py:162](backend/app/services/handoff.py#L162)) y el link de respaldo en
  texto plano ([handoff.py:196](backend/app/services/handoff.py#L196)) usan esa URL.
- [config.py:9](backend/app/core/config.py#L9) — `frontend_url` tiene **default
  `http://localhost:5173`**. Si el `.env` del backend que envía el correo no define
  `FRONTEND_URL`, el botón apunta a localhost → muerto en el teléfono o en cualquier
  otra máquina. **Esta es la hipótesis principal del vault y el código la confirma
  como posible**: nada valida ni advierte hoy sobre ese default en un entorno
  desplegado.
- [consent.py:83-98](backend/app/services/consent.py#L83-L98) — `ConsentService.capture`
  envía el correo *best-effort* (nunca rompe el cierre; error solo se loguea). Aquí es
  donde se puede cortar/advertir el envío con link inválido sin romper el flujo.
- [config.py:10](backend/app/core/config.py#L10) — `backend_public_url` ya existe y
  es la **señal natural de "backend desplegado"**: solo se configura en producción
  (hoy la usa el registro del webhook de Telegram,
  [telegram_client.py:31-34](backend/app/services/telegram_client.py#L31-L34)).
- [handoff.py (router):37-53](backend/app/api/routes/handoff.py#L37-L53) —
  `GET /api/v1/handoff/{token}` (404 si no existe) y `POST /{token}/finalize`.
  El token se resuelve por query indexada contra Postgres/SQLite
  ([applications.py:96-104](backend/app/repositories/applications.py#L96-L104)).
- [InsurerView.vue](frontend/src/features/aseguradora/InsurerView.vue) +
  [router/index.js:61](frontend/src/router/index.js#L61) — la página pública funciona
  sin sesión del chat (todo sale del token de la URL) y ya maneja 404
  ("No encontramos tu solicitud") y error de red. **E2 no necesita cambios.**
- [test_handoff.py:143-149](backend/tests/test_handoff.py#L143-L149) — ya existe un
  test de que el link usa `settings.frontend_url`; lo que NO existe es un test de que
  un backend desplegado nunca envíe el link con localhost.
- [backend/.env.example:4](backend/.env.example#L4) — documenta `FRONTEND_URL` solo
  como "URL del frontend permitida por CORS"; no menciona que también es la base del
  link del correo de handoff (por eso es fácil olvidarla en el deploy).

**Diagnóstico de las 3 hipótesis del vault contra el código:**

1. **Link a localhost** — plausible y la más probable: default de `config.py:9` +
   `.env.example` que no explica el doble rol de `FRONTEND_URL`. Es un bug de
   configuración del deploy, no de lógica.
2. **Token inexistente donde apunta el link** — plausible como efecto cruzado: el
   token vive en la base del backend que capturó el consentimiento
   ([applications.py:49-75](backend/app/repositories/applications.py#L49-L75)). Si el
   correo salió de un backend local (SQLite) y el link se abre contra producción
   (Postgres), la página da 404 legítimo. No requiere cambio de código: requiere que
   el flujo del demo corra **de punta a punta contra producción**.
3. **Cliente de correo bloqueando el link** — poco probable: el correo ya incluye el
   link crudo en texto como respaldo ([handoff.py:196](backend/app/services/handoff.py#L196));
   se descarta o confirma viendo el HTML crudo del correo real en la Fase 1.

**Conclusión del análisis**: el arreglo es (a) configurar `FRONTEND_URL` en el
backend de producción (Dokploy — fuera del repo), y (b) blindar el código para que un
backend desplegado jamás envíe un correo con link a localhost (test del criterio 4).

## Decisiones pendientes (bloqueantes)

- **Acceso a producción para las Fases 1 y 3**: se necesita ver las env vars del
  backend en Dokploy (¿`FRONTEND_URL` está definida?) y poder editarlas. Sin ese
  acceso, la Fase 2 (código) puede avanzar igual, pero el bug no queda cerrado.
- *(decisión tomada, no bloqueante — validar en el checkpoint de la Fase 2)*:
  comportamiento del guard: si `backend_public_url` está configurada (señal de
  deploy) y `frontend_url` apunta a localhost, **no se envía el correo** y se loguea
  `ERROR` explícito (falla ruidosa, criterio 4). Alternativa descartada: enviar con
  advertencia — entregaría igual un botón muerto al cliente.

## Principios

- Verde por fase: `pytest` del backend en verde al cierre de cada fase que toque código.
- Bugfix mínimo y aditivo: **cero cambios** en el contrato HTTP front↔back, en E2 ni
  en el HTML del correo; solo un guard + logging + documentación de env var.
- Config por env vars: el dominio de producción **no se hardcodea**; se corrige en el
  `.env` del deploy y se documenta en `.env.example`.
- Sin dependencias nuevas.
- El fix de configuración (Dokploy) y el fix de código (guard) son independientes:
  el primero arregla el demo hoy, el segundo evita la regresión en el próximo deploy.

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | ambos | Ninguno | 5m | _(sin commit)_ |
| 1 | Reproducir y diagnosticar con correo real | backend (read-only) + prod | Ninguno | 15m | _(sin commit)_ |
| 2 | Guard anti-localhost + tests + doc de env var | backend | Aditivo | 25m | `fix(back): block handoff email with localhost link on deploy` |
| 3 | Configurar producción y verificar arco completo | prod (Dokploy, fuera del repo) | Config | 15m | _(sin commit; solo config)_ |

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: ambos
**Objetivo**: confirmar que el punto de partida está verde antes de tocar nada.
**Archivos afectados**: ninguno (solo lectura).
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. (backend) Desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` — la suite
   completa debe estar verde (incluye [test_handoff.py](backend/tests/test_handoff.py),
   [test_consent.py](backend/tests/test_consent.py),
   [test_handoff_endpoint.py](backend/tests/test_handoff_endpoint.py)).
2. (frontend) Desde `frontend/`: `npm run build` — debe compilar sin errores (no se
   tocará el frontend, pero valida la base).
3. (backend) Verificar qué hay en `backend/.env` local: ¿`FRONTEND_URL` definida?
   ¿`RESEND_API_KEY` y `RESEND_FROM` configuradas? (necesarias para la Fase 1).

**Pruebas / verificación**: los dos comandos de arriba en verde.
**Riesgos**: si la suite ya está roja, detenerse y reportar antes de seguir.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit — fase de solo lectura)_

---

## Fase 1 — Reproducir y diagnosticar con correo real

**Proyecto**: backend (read-only) + producción
**Objetivo**: reproducir el clic desde un correo real recibido y fijar la **causa
exacta** (criterio 1 del vault) antes de escribir el fix.
**Archivos afectados**: ninguno del repo (diagnóstico); hallazgos se presentan en el
checkpoint para que el usuario los documente en la nota E7 del vault (fuera del
ámbito de escritura de los agentes).
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. (prod) Revisar en Dokploy las env vars del backend desplegado: valor real de
   `FRONTEND_URL` (hipótesis 1) y `DATABASE_URL` (hipótesis 2). Este paso lo hace el
   usuario o se salta si no hay acceso en la sesión.
2. (prod) Disparar el flujo de cierre **contra el backend de producción** con correo
   destino `carlos@kokomi.io` (chat web de producción hasta el consentimiento, o
   `POST` al endpoint de consentimiento de prod si el chat no está sembrado —
   relacionado con C5/base vacía).
3. Abrir el correo recibido, inspeccionar el **HTML crudo**: ¿a qué host apunta
   `href` del botón? (localhost → hipótesis 1 confirmada; dominio correcto →
   seguir con 4). De paso se descarta/confirma la hipótesis 3 (cliente de correo
   reescribiendo el link).
4. Hacer clic desde incógnito: si responde 404, verificar con
   `curl https://<backend-prod>/api/v1/handoff/{token}` si el token existe en el
   Postgres de producción (hipótesis 2).
5. Registrar la causa exacta y presentarla en el checkpoint (para la nota del vault).

**Pruebas / verificación**: correo real recibido en `carlos@kokomi.io`; causa
identificada de forma reproducible (no por deducción).
**Riesgos**: sin acceso a Dokploy o sin claves de Resend en prod, el diagnóstico queda
parcial — en ese caso se avanza con la hipótesis 1 (respaldada por el código) y la
Fase 3 cierra la verificación cuando haya acceso.

🛑 **CHECKPOINT** — Detente aquí. Presenta la causa exacta encontrada. No inicies la
Fase 2 sin aprobación del usuario.
**Commit sugerido**: _(sin commit — fase de diagnóstico)_

---

## Fase 2 — Guard anti-localhost + tests + doc de env var

**Proyecto**: backend
**Objetivo**: que un backend desplegado **nunca** envíe el correo de handoff con un
link a localhost (criterio 4: falla ruidosa en vez de botón muerto), y que
`.env.example` explique el doble rol de `FRONTEND_URL` para que no se olvide en el
próximo deploy.
**Archivos afectados**:
- [backend/app/services/consent.py](backend/app/services/consent.py) — guard en `capture()`
- [backend/tests/test_consent.py](backend/tests/test_consent.py) — tests del guard
- [backend/.env.example](backend/.env.example) — documentación de `FRONTEND_URL`
**Impacto en contrato API (front↔back)**: No — no cambia rutas, shapes, status codes
ni env vars nuevas (solo documenta mejor una existente). El HTML del correo no cambia.
**Acciones** (TDD-light: tests primero):
1. Tests en [test_consent.py](backend/tests/test_consent.py) (con `monkeypatch` sobre
   `settings`, patrón de [test_handoff.py:143](backend/tests/test_handoff.py#L143)):
   - `backend_public_url` configurada + `frontend_url` con `localhost` + email →
     **no** se llama a `resend_client.send_email` y se loguea `ERROR` (verificable
     con `caplog`) que menciona `FRONTEND_URL`.
   - `backend_public_url` configurada + `frontend_url` = dominio real → el correo
     **sí** se envía y el HTML contiene el dominio.
   - `backend_public_url` vacía (desarrollo local) + `frontend_url` localhost → el
     correo se envía normal (no romper el flujo local de desarrollo).
2. Implementar el guard en `ConsentService.capture()`
   ([consent.py:83](backend/app/services/consent.py#L83)): antes de construir/enviar
   el correo, si `settings.backend_public_url` no está vacía y
   `settings.frontend_url` apunta a `localhost`/`127.0.0.1`, loguear
   `logger.error("FRONTEND_URL apunta a localhost en un backend desplegado; no se envía el correo de handoff ...")`
   y **saltar el envío** (el cierre de la solicitud sigue intacto, mismo espíritu
   best-effort de siempre).
3. Actualizar [backend/.env.example](backend/.env.example): ampliar el comentario de
   `FRONTEND_URL` — "URL pública del frontend: se usa para CORS **y como base del
   link del correo de handoff** (`/aseguradora/{token}`); en producción debe ser el
   dominio real (p. ej. `https://colsubsidio.zyvra.lat`), nunca localhost".

**Pruebas / verificación**: desde `backend/`, `.venv\Scripts\python.exe -m pytest -q`
en verde (suite completa, incluidos los 3 tests nuevos). Ruta negativa cubierta por
el primer test (misconfiguración → error logueado, nunca 500 ni correo roto).
**Riesgos**: el guard depende de que `backend_public_url` sea señal fiable de "estoy
desplegado" — hoy lo es (solo prod la define, para el webhook de Telegram); si algún
día un dev la define en local, solo perdería el correo local (log lo dice claro).

🛑 **CHECKPOINT** — Detente aquí. Muestra el diff y el resultado de pytest. No inicies
la Fase 3 sin aprobación del usuario.
**Commit sugerido**: `fix(back): block handoff email with localhost link on deploy`

---

## Fase 3 — Configurar producción y verificar arco completo

**Proyecto**: producción (Dokploy — fuera del repo; sin cambios de código)
**Objetivo**: cerrar los criterios 2 y 3 del vault: botón funcionando en producción,
desde incógnito y teléfono, hasta "Tu póliza quedó activa (simulación)".
**Archivos afectados**: ninguno del repo (env vars del deploy).
**Impacto en contrato API (front↔back)**: No (config de despliegue).
**Acciones**:
1. (prod) En Dokploy, backend: definir/corregir `FRONTEND_URL=https://colsubsidio.zyvra.lat`
   y redeploy (o reinicio) del servicio. De paso confirma que el fix de la Fase 2
   está desplegado.
2. (prod) Repetir el flujo de cierre contra producción con `carlos@kokomi.io`
   (mismo procedimiento de la Fase 1, paso 2) — el token queda así en el Postgres de
   prod (cubre la hipótesis 2).
3. Verificar el arco completo desde el correo recibido:
   - El botón abre `https://colsubsidio.zyvra.lat/aseguradora/{token}` en incógnito
     (sin sesión del chat) y desde el teléfono.
   - "Continuar al pago" → **"Tu póliza quedó activa (simulación)"**.
   - `curl https://<backend-prod>/api/v1/handoff/{token}` devuelve
     `"state": "finalizada_demo"`.
4. Presentar en el checkpoint la evidencia (URLs, capturas) para marcar los criterios
   del vault y desbloquear H8.

**Pruebas / verificación**: las del punto 3 (manuales, contra producción). Caso
negativo: un token inventado en `/aseguradora/xxx` debe mostrar "No encontramos tu
solicitud" (404 controlado, ya implementado por E2).
**Riesgos**: CORS — `FRONTEND_URL` también alimenta `allow_origins`
([main.py:30](backend/app/main.py#L30)); si prod ya funcionaba con el chat web, ya
estaba bien o hay otra fuente — verificar que el chat siga funcionando tras el cambio.

🛑 **CHECKPOINT final** — Presenta la evidencia de los criterios de aceptación.
**Commit sugerido**: _(sin commit — solo configuración de despliegue)_
