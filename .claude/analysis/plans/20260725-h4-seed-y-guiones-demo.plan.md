# Plan — H4: Seed y guiones del demo por categoría · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-25 · **Tipo**: plan de implementación por fases.
> **Base**:
> [20260725-c2-base-afiliados-postgres.plan.md](.claude/analysis/plans/20260725-c2-base-afiliados-postgres.plan.md)
> (✅ en master: tabla `afiliados` con columnas sintéticas `sint_*` deterministas por
> SERIE — H4 cura SERIEs de esa tabla),
> [20260725-b3-propension-multicategoria-explicable.plan.md](.claude/analysis/plans/20260725-b3-propension-multicategoria-explicable.plan.md)
> (✅ en master: motor de propensión que decide la categoría — H4 verifica que cada
> SERIE curada gana la categoría esperada),
> [20260725-b2-catalogo-4-categorias-restantes.plan.md](.claude/analysis/plans/20260725-b2-catalogo-4-categorias-restantes.plan.md)
> (✅ en master: catálogo con las 5 categorías y tarifas de los guiones) y
> [20260725-c3-conversaciones-solicitudes-postgres.plan.md](.claude/analysis/plans/20260725-c3-conversaciones-solicitudes-postgres.plan.md)
> (✅ en master: tablas `conversaciones`/`solicitudes` — el seed del panel escribe ahí).
> Tarea del vault: `07 - Tareas/Feature H - Entrega y despliegue/H4 - Seed y guiones del demo por categoria.md`
> (depende de **B2 ✅** y **C2 ✅**; **bloquea H5**; capa integración; estimación 2h).
> **Proyectos afectados**: backend (fases 1–2) + vault fuera del repo (fase 3).
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

El demo es reproducible a voluntad:

1. **5 SERIEs reales curadas** (una por categoría) cuyo perfil de la base —columnas
   reales + sintéticas deterministas— hace que el motor de propensión recomiende la
   categoría esperada, verificado por script y por conversación real grabada.
2. **Datos sembrados** en `conversaciones`/`solicitudes` (6–8 conversaciones/ventas de
   muestra) para que el panel de negocio (G1/G2) no aparezca vacío en el primer
   acceso del jurado.
3. **Guiones del vault actualizados** con las frases exactas que escribirá quien
   grabe el video (líder: Hogar), alineadas al producto real (tarjetas, consentimiento
   en UI, aseguradora simulada — no el borrador pre-D3/D4/E2).

Las SERIEs reales se documentan en una **nota interna del vault**, nunca en este repo
público (misma regla que la data real: [cargar_afiliados.py:12-13](backend/app/scripts/cargar_afiliados.py#L12-L13)).

## Contexto / hallazgos del análisis

**Cómo llega un perfil de la base al motor.**
[affiliates.py:253-276](backend/app/repositories/affiliates.py#L253-L276)
(`_record_to_profile`) arma el `AffiliateProfile` desde la tabla `afiliados`:
`sint_tipo_vivienda → property_type`, `sint_tiene_hijos → has_children`,
`sint_tiene_vehiculo → has_vehicle`, `sint_tiene_credito → has_credit`,
`zone = "urban"` si hay ciudad. Las sintéticas son deterministas por SERIE
([synthetic.py:22-31](backend/app/services/synthetic.py#L22-L31), sha256 por campo),
así que **la curación es reproducible**: la misma SERIE siempre produce el mismo
perfil y el mismo ranking.

**Qué puede ganar cada categoría desde la base (sin datos declarados).** Con las
reglas de [propensity.py:97-247](backend/app/services/propensity.py#L97-L247) y un
perfil de base (que **no** trae `stratum` ni `has_family` — esas señales solo llegan
declaradas en conversación):

| Categoría | Señales alcanzables desde la base | Score máx. aprox. |
|---|---|---|
| movilidad | `sint_tiene_vehiculo` (0.75) + young_driver (0.05) | 0.80 |
| credito | `sint_tiene_credito` (0.70) + working_age (0.10) | 0.80 |
| vida | `sint_tiene_hijos` (0.50) + life_stage (0.15) + segmento RHO/LAMBDA (0.10) | 0.75 |
| hogar | `sint_tipo_vivienda` (0.45) + zone_risk (0.10) — `income_tier` exige `stratum`, ausente en base | 0.55 |
| accidentes | 18-25 (0.40) + urban (0.10) — `no_dependents` exige `has_family is False`, ausente en base | 0.50 |

Consecuencia: la curación selecciona por **categoría ganadora del ranking** (no por
score absoluto), y para hogar/accidentes el perfil debe además **no** tener vehículo,
crédito ni hijos sintéticos (que pesan más). Hay SERIEs así con probabilidad alta:
p. ej. hogar ≈ (vivienda 65%) × (sin vehículo 72%) × (sin crédito 65%) × (sin hijos
35–75%) — decenas de miles de candidatos en 500k. El script de la Fase 1 lo
comprueba, no lo asume.

**Dónde escribe el seed del panel.** El panel (G1, aún no construido) leerá
`conversaciones` y `solicitudes`; el documento completo va serializado en la columna
`data` ([conversations.py:39-60](backend/app/repositories/conversations.py#L39-L60),
[applications.py:45-71](backend/app/repositories/applications.py#L45-L71)). Sembrar
usando los schemas reales ([conversation.py:86-94](backend/app/schemas/conversation.py#L86-L94)
`ConversationResponse`, [conversation.py:60-71](backend/app/schemas/conversation.py#L60-L71)
`ConsentedApplication`) garantiza que el panel futuro renderice transcripción, monto
y hora sin adaptadores. Cada `Message` ya sella `timestamp` ISO-8601
([conversation.py:17-25](backend/app/schemas/conversation.py#L17-L25), C4 ✅).

**Cómo generar solicitudes coherentes sin disparar correos.**
[consent.py:32-81](backend/app/services/consent.py#L32-L81) (`ConsentService.capture`)
genera `evidence_hash`, `handoff_token` y aseguradora simulada, y **solo envía correo
si hay `email`** — el seed llama `capture(email=None)` y luego
`finalize_by_token(token)` ([consent.py:114-128](backend/app/services/consent.py#L114-L128))
para dejar las ventas en `finalizada_demo`. Cero Resend, hash y token reales.

**Cotizaciones reales, no inventadas.** El seed usa
[quote.py:25-72](backend/app/services/quote.py#L25-L72) (`QuoteService.calculate_quote`)
y [propensity.py:277](backend/app/services/propensity.py#L277)
(`PropensityService.evaluate`) para que recomendación y prima mensual del panel
coincidan con lo que el jurado vería cotizando en vivo.

**Patrón de script batch ya establecido.**
[cargar_afiliados.py](backend/app/scripts/cargar_afiliados.py) (`python -m
app.scripts.…`, engine inyectable, `--replace`, resumen impreso) es la plantilla de
los dos scripts nuevos; sus tests ([test_cargar_afiliados.py](backend/tests/test_cargar_afiliados.py))
muestran el patrón de engine SQLite en memoria.

**Los guiones del vault quedaron desactualizados frente al producto real.** El
borrador (`02 - Idea y Negocio/Guiones de Demo Conversacional (MVP)`) es pre-D3/D4/E2:
promete correos de Sura/Bolívar/Mapfre y pago por link enviado por la aseguradora.
El flujo real hoy: tarjetas de recomendación/cotización/comparador (D3 ✅), cierre con
consentimiento y éxito en la UI (D4 ✅), página de aseguradora simulada
`/aseguradora/{token}` (E2 ✅), correo de handoff (E1 ✅, con límite de destinatario
hasta que E5 cierre). La Fase 3 reescribe las frases sobre el flujo real — y cuida
que lo declarado en el chat no contradiga el perfil de la SERIE curada (un dato
declarado en A4 podrá voltear el ranking; hoy el riesgo es narrativo: p. ej. en el
guion de Hogar el presentador no debe decir "tengo carro").

**Env vars**: cero nuevas. Los scripts usan `DATABASE_URL` vía
[db.get_engine()](backend/app/repositories/db.py) igual que la carga de afiliados
([.env.example:27](backend/.env.example#L27)).

## Decisiones pendientes (bloqueantes)

(ninguna — dos defaults ajustables en los checkpoints, no bloquean el arranque:)

1. **Categoría líder del video: Hogar** (propuesta del vault, "ajustable al aprobar
   el plan"). El plan la asume; si cambia, solo cambia qué guion se pule más.
2. **Mezcla del seed: 5 ventas cerradas (una por categoría) + 2 conversaciones en
   curso** (`quote_ready` y `awaiting_consent`) = 7, dentro del rango 6–8 pedido.
3. **Seed en producción**: la tabla de prod se siembra corriendo el mismo script en
   el VPS — mismo viaje que C5/H6 (anotarlo en esas tareas), fuera de este plan.

## Principios

- Verde por fase: `pytest` del backend en verde al cierre de cada fase de código.
- Solo backend toca código; el frontend no cambia (el panel es G1/G2, otra tarea).
- Contrato HTTP intacto: H4 no agrega ni cambia endpoints.
- Aditivo antes que destructivo: los scripts nunca tocan datos que no sembraron
  (`--replace` solo borra `session_id LIKE 'seed-demo-%'`).
- Sin dependencias nuevas; sin datos reales (SERIEs) commiteados al repo.
- Reproducibilidad: nada de `random` — curación determinista por construcción
  (sintéticos por sha256) y seed con contenidos fijos.

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | backend | Ninguno | 5m | _(sin commit)_ |
| 1 | Script de curación de SERIEs por categoría | backend | Aditivo | 35m | `feat(back): add demo serie curation script per category` |
| 2 | Script de seed del panel (conversaciones + ventas) | backend | Aditivo | 45m | `feat(back): seed demo conversations and sales for panel` |
| 3 | Curaduría real + guiones definitivos del vault | ninguno (vault, fuera del repo) | Ninguno en el repo | 35m | _(sin commit en este repo)_ |

Total ≈ 2h — coherente con la estimación del vault.

---

## Fase 0 — Pre-flight (read-only)

**Proyecto**: backend
**Objetivo**: confirmar que la base sobre la que se construye está sana.
**Archivos afectados**: ninguno (solo lectura/ejecución).
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` — suite en verde
   (los tests `*_live` se saltan sin API key, es lo esperado).
2. Verificar que el Postgres local (docker compose) está arriba y la tabla
   `afiliados` tiene los ~500k de C2: `SELECT count(*) FROM afiliados;` (o vía el
   health de integraciones). Si está vacía, correr antes la carga de C2 — la Fase 1
   puede desarrollarse con fixtures, pero la Fase 3 exige la base real local.
3. Confirmar que el catálogo trae las 5 categorías (B2): `hogar`, `vida`,
   `accidentes`, `movilidad`, `credito`.

**Pruebas / verificación**: las de arriba; no se escribe nada.
**Riesgos**: tabla `afiliados` local vacía → bloquea solo la Fase 3 (curaduría real).

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit)_

---

## Fase 1 — Script de curación de SERIEs por categoría

**Proyecto**: backend
**Objetivo**: encontrar, de forma reproducible, SERIEs reales cuyo perfil gana cada
categoría — sin copiar data real al repo.
**Archivos afectados**:
- [backend/app/scripts/](backend/app/scripts/) → nuevo `curar_series.py`
- `backend/tests/` → nuevo `test_curar_series.py`

**Impacto en contrato API (front↔back)**: No (script CLI, cero endpoints).
**Acciones**:
1. Crear `app/scripts/curar_series.py` (mismo patrón CLI que
   [cargar_afiliados.py](backend/app/scripts/cargar_afiliados.py)):
   - Recorre la tabla `afiliados` en lotes (`SELECT` paginado por `serie`), convierte
     cada registro con `AffiliateRepository._record_to_profile` (exponer un accesor
     público si hace falta, como se hizo con `parsed_profiles()`) y evalúa
     `PropensityService().evaluate(profile)`.
   - Clasifica un perfil como **candidato de la categoría X** si X es la primera del
     `ranking` y le saca **margen ≥ 0.10** a la segunda (evita empates frágiles que
     un dato declarado voltearía).
   - Se detiene cuando junta `--candidatos-por-categoria` (default 3) para las 5
     categorías o alcanza `--max-filas` (default 100000, para no barrer 500k si no
     hace falta).
   - Imprime por categoría: SERIE, score, razones (código + evidencia) y el
     runner-up con su score — todo lo que la nota interna del vault necesita.
   - Instanciar `PropensityService`/`CatalogService` una sola vez fuera del loop.
2. Tests (`test_curar_series.py`), con engine SQLite en memoria (patrón de
   [test_cargar_afiliados.py](backend/tests/test_cargar_afiliados.py)): sembrar
   `AffiliateRecord`s fabricados para que exista al menos un ganador por categoría
   (p. ej. vehículo→movilidad, crédito→credito, hijos+26-40→vida, solo
   vivienda→hogar, 18-25 sin nada→accidentes) y asertar que el script: (a) devuelve
   candidatos de las 5 categorías, (b) cada candidato gana su categoría con el
   margen exigido, (c) es determinista (dos corridas → mismo resultado), (d) con
   tabla vacía termina limpio reportando 0 candidatos (no truena).

**Pruebas / verificación**: `.venv\Scripts\python.exe -m pytest -q` en verde; corrida
manual rápida contra el Postgres local (`python -m app.scripts.curar_series`) viendo
candidatos reales impresos.
**Riesgos**: escanear 500k con el motor en Python es O(n) — mitigado con paginado,
early-stop y `--max-filas`; si alguna categoría no aparece en las primeras 100k
filas, subir el tope solo para esa corrida.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `feat(back): add demo serie curation script per category`

---

## Fase 2 — Script de seed del panel (conversaciones + ventas)

**Proyecto**: backend
**Objetivo**: que el panel muestre datos desde el primer acceso del jurado: 7
conversaciones de muestra (5 ventas cerradas —una por categoría— + 2 en curso),
re-sembrables a voluntad sin duplicar ni tocar datos reales.
**Archivos afectados**:
- [backend/app/scripts/](backend/app/scripts/) → nuevo `seed_demo.py`
- `backend/tests/` → nuevo `test_seed_demo.py`

**Impacto en contrato API (front↔back)**: No — escribe en las tablas
`conversaciones`/`solicitudes` que G1 leerá; no cambia rutas ni shapes. (Coordinación
con G1: al sembrar con `ConversationResponse`/`ConsentedApplication` reales, el
contrato del panel queda definido por los schemas ya existentes.)
**Acciones**:
1. Crear `app/scripts/seed_demo.py` (CLI `python -m app.scripts.seed_demo
   [--replace]`):
   - **Datos**: 7 conversaciones con `session_id` prefijo `seed-demo-` (p. ej.
     `seed-demo-hogar`, `seed-demo-vida`, …, `seed-demo-en-curso-1/2`). Transcripciones
     cortas (4–6 mensajes user/bot) tomadas de los guiones por categoría, con
     `timestamp` de cada `Message` y `created_at`/`updated_at` escalonados hacia
     atrás en las últimas ~24h (el panel se ve "vivo", no 7 filas del mismo segundo).
   - **Coherencia con los motores**: por categoría, armar el `ProfileData` que la
     gana, y generar `Recommendation` con `PropensityService.evaluate` y
     `QuoteDetail` con `QuoteService.calculate_quote` — nada de montos inventados.
   - **Ventas (5)**: `ConsentService.capture(session_id, …, email=None)` (cero
     Resend) + `finalize_by_token(token)` → solicitud en `finalizada_demo` con
     `evidence_hash`, token y aseguradora reales; la conversación asociada se guarda
     en estado `finalizada_demo` con su `application` embebida.
   - **En curso (2)**: una en `quote_ready` y una en `awaiting_consent`, sin
     solicitud.
   - **Idempotencia**: `--replace` borra únicamente `session_id LIKE 'seed-demo-%'`
     en ambas tablas antes de sembrar; sin `--replace`, si ya existen ids seed,
     abortar con mensaje claro. Nunca toca sesiones reales.
   - Resumen impreso: conversaciones sembradas, solicitudes, ids.
2. Tests (`test_seed_demo.py`), engine SQLite en memoria + monkeypatch de
   `db.get_engine` (patrón del conftest):
   - Siembra → 7 conversaciones y 5 solicitudes; estados esperados por id;
     `find()` de una venta devuelve `ConsentedApplication` válida (schema roundtrip).
   - Re-siembra con `--replace` → mismos conteos (no duplica); una conversación real
     previa (id sin prefijo) sobrevive intacta.
   - Ningún correo: monkeypatch del cliente Resend que falle si se llama.
   - Caso negativo: segunda corrida sin `--replace` → salida de error limpia, DB
     intacta.

**Pruebas / verificación**: `pytest -q` en verde; corrida manual contra el Postgres
local y `SELECT session_id, estado FROM conversaciones WHERE session_id LIKE
'seed-demo-%';` mostrando las 7; levantar el backend y comprobar que el flujo normal
del chat sigue intacto.
**Riesgos**: colisión de ids con datos reales (mitigada por el prefijo reservado);
si G1 decide filtrar por `canal`, hoy se siembra `canal=None` — decisión a
sincronizar con quien tome G1 (una línea si cambia).

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 3 sin aprobación del usuario.
**Commit sugerido**: `feat(back): seed demo conversations and sales for panel`

---

## Fase 3 — Curaduría real + guiones definitivos del vault

**Proyecto**: ninguno (vault `colsubsidio-brain`, fuera del monorepo — sin commit en
este repo; la escritura la hace el orquestador/usuario, no los agentes)
**Objetivo**: dejar el demo listo para grabar: SERIEs elegidas y verificadas en el
chat real, frases exactas por categoría en el vault.
**Archivos afectados** (vault, fuera del repo):
- `02 - Idea y Negocio/Guiones de Demo Conversacional (MVP).md` (frases definitivas)
- `06 - Pitch/Guion del demo.md` (personaje/flujo con la SERIE de Hogar)
- Nueva nota interna con las 5 SERIEs curadas (p. ej. `06 - Pitch/SERIEs curadas del
  demo.md`) — **nunca en el repo público**
- `07 - Tareas/.../H4 - Seed y guiones del demo por categoria.md` (criterios ✓)

**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Correr `python -m app.scripts.curar_series` contra el Postgres local (500k) y
   elegir 1 SERIE por categoría (entre los candidatos, preferir los de razones más
   contables para el pitch — p. ej. para vida un segmento RHO con evidencia de
   droguería).
2. Verificación manual grabada (criterio del vault): para cada SERIE, abrir el chat,
   saludar con la SERIE, y confirmar que la recomendación es la esperada con ≥2
   razones. Guardar captura/video corto por categoría (respaldo del sábado).
3. Correr `python -m app.scripts.seed_demo --replace` en local y abrir el panel (si
   G1/G2 ya está) o verificar por SQL que los datos están.
4. Reescribir los guiones del vault sobre el **flujo real** (tarjetas D3, cierre D4,
   página de aseguradora E2, correo E1): frases exactas del usuario por categoría,
   pulido máximo en **Hogar** (líder), y cuidando que ninguna frase declare datos que
   contradigan el perfil de la SERIE (no "voltear" la recomendación en cámara).
5. Anotar en las tareas C5/H6 del vault: al correr la carga en el VPS, correr también
   `seed_demo --replace` (panel de prod con datos antes del jurado).

**Pruebas / verificación**: los 3 criterios de aceptación de H4 marcados en el vault
con evidencia (capturas + SERIEs en la nota interna + guiones actualizados).
**Riesgos**: si E5 (correo a cualquier destinatario) no ha cerrado, el guion usa el
buzón de prueba autorizado — anotarlo en el guion para no improvisar en cámara.

🛑 **CHECKPOINT final** — H4 queda completa; desbloquea H5 (hardening pre-entrega).
**Commit sugerido**: _(sin commit en este repo — los cambios viven en el vault)_
