# Plan — B5: Preguntas por categoría según la Matriz (+ RUNT simulado) · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-25 · **Tipo**: plan de implementación por fases.
> **Base**: [20260725-a3-orquestador-conversacional-llm.plan.md](.claude/analysis/plans/20260725-a3-orquestador-conversacional-llm.plan.md)
> (orquestador + contrato de tools), [20260725-a2-contrato-herramientas-agente.plan.md](.claude/analysis/plans/20260725-a2-contrato-herramientas-agente.plan.md)
> (patrón declaration/handler/ToolContext),
> [20260725-b4-cotizador-multicategoria-ajustar-comparar.plan.md](.claude/analysis/plans/20260725-b4-cotizador-multicategoria-ajustar-comparar.plan.md)
> (dejó los factores `vehicle_type`/`debt_balance` **neutros hasta B5** — esta tarea
> los activa). Tarea del brain: **B5 — Preguntas por categoría según la Matriz
> (+ RUNT/Fasecolda simulados)** (depende de B1 ✔ y A3 ✔). Fuentes de negocio:
> Matriz de Perfilamiento (5 categorías × 2 vías) y Guiones de Demo (escenario 3:
> placa `XYZ-987` → "Chevrolet Spark 2020").
> **Proyectos afectados**: backend.
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

El orquestador sabe, **por categoría**, qué preguntar y qué deducir (principio
"Fricción Cero" de la Matriz): a un afiliado no se le pregunta lo que la base ya
sabe; a un prospecto todo lo deducible pasa a preguntado sin cambiar el flujo. Para
Movilidad, la placa dispara una consulta a un **RUNT/Fasecolda simulado** (etiquetado
como simulación, misma filosofía que el handoff) que devuelve marca/modelo/año
verosímiles — y de paso activa el factor `vehicle_type` que B4 dejó neutro.

## Contexto / hallazgos del análisis

**La Matriz (vault, definitiva)** define por categoría el trío
`dato → vía afiliado (preguntar | deducido base | deducido API) → vía no afiliado`.
Síntesis operativa para el MVP (solo los datos que el motor/flujo actual puede usar
o que el bot debe saber NO preguntar):

- **Vida/Personal**: edad, género, ocupación e ingresos = **deducidos de base**
  (SSO/PILA) para afiliados; fumador/deportes extremos = siempre preguntados.
- **Movilidad**: placa = preguntada; marca/línea/modelo/año = **deducidos vía RUNT**;
  edad/ciudad = base para afiliados; uso del vehículo = preguntado.
- **Hogar**: ciudad/estrato = base para afiliados; tipo de inmueble, rol
  (dueño/inquilino), medidas de seguridad = preguntados.
- **Accidentes** (≈ Personal) y **Crédito**: edad/género/entidad/saldo = base para
  afiliados (saldo → factor `debt_balance` de B4, hoy sin campo de perfil).

**Dónde encaja en el código real:**

- [agent_tools.py](backend/app/services/agent_tools.py) — patrón exacto a seguir:
  `declaration` Gemini + `handler(args, ctx)` + registro en `AGENT_TOOLS`
  ([línea 429](backend/app/services/agent_tools.py#L429)); `execute_tool` ya blinda
  errores. `ToolContext` posee el estado; los precios/perfiles nunca viajan por el
  LLM.
- [`_perfilar_cliente`](backend/app/services/agent_tools.py#L133) ya resuelve
  afiliado vs declarado y devuelve `fuente: "base"|"declarado"` — pero **esa fuente
  no se persiste** en el perfil: `ProfileData` no tiene cómo recordar que vino de la
  base. Para que `campos_pendientes` funcione entre turnos hace falta persistirla
  (campo aditivo `source`).
- [ProfileData](backend/app/schemas/conversation.py#L28-L36) tiene
  `property_type/zone/stratum/age_range/has_family/has_children/has_vehicle/has_credit`
  — sin género (la base SÍ lo tiene:
  [AffiliateProfile.gender](backend/app/models/affiliate.py#L39)), sin datos de
  vehículo y sin saldo de deuda. Los factores B4 `vehicle_type` y `debt_balance`
  ([productos.json](backend/app/data/catalogo/productos.json)) hoy son neutros por
  eso.
- [SYSTEM_PROMPT](backend/app/services/orchestrator.py#L53-L89) — reglas duras
  numeradas 1-7; la guía "consulta qué falta antes de preguntar" entra como regla
  nueva. [`_build_status_summary`](backend/app/services/orchestrator.py#L132-L165)
  inyecta el estado del funnel por turno — lugar natural para un renglón de campos
  conocidos/pendientes de la categoría vigente (la recomendación ya vive en el ctx).
- **Simulaciones etiquetadas**: el patrón existe (aseguradora simulada del handoff,
  sintéticos `sint_*` de C2 con docstring de transparencia) — el RUNT simulado va en
  `app/services/integrations/` con el mismo etiquetado en docstring y en el response
  (`"fuente": "RUNT simulado"`).
- Tests de conversación con LLM mockeado: patrón ya montado en
  [test_orchestrator.py](backend/tests/test_orchestrator.py) y
  [test_agent_tools.py](backend/tests/test_agent_tools.py) (mock de
  `generate_reply` con guiones de tool calls) — los criterios 1 y 2 se prueban así,
  sin gastar cuota Gemini.
- Guion demo escenario 3 (vault): placa `XYZ-987` → "Chevrolet Spark 2020" citado
  por el bot antes de cotizar.

**Restricción de alcance (hackathon)**: la Matriz trae datos que el motor actual no
consume (IMC, microchip de mascota, año de construcción…). B5 NO agrega campos
muertos: solo entran al perfil los campos que (a) el motor usa (factores B4), (b) el
bot debe saber no preguntar (edad/género/ocupación), o (c) la demo cita (vehículo
RUNT). El resto vive solo como texto en la config de la Matriz (para que el bot
sepa preguntarlo si la conversación llega ahí, sin persistencia estructurada).

## Decisiones pendientes (bloqueantes)

(ninguna — resueltas en el análisis:)

- **`ProfileData` gana campos aditivos**: `source` ("base"|"declarado"),
  `gender`, `vehicle_plate`, `vehicle_brand`, `vehicle_line`, `vehicle_year`,
  `vehicle_type` ("auto"|"moto"), `vehicle_use`, `debt_balance` ("<50M"|"50-150M"|
  ">150M"). Todos opcionales → el shape del perfil en la API crece de forma
  aditiva (el frontend lo ignora; cero breaking).
- **`campos_pendientes` es tool Y renglón del status summary**: la tool da el
  detalle bajo demanda; el renglón por turno evita que el modelo pregunte de más
  aunque no llame la tool. Doble cinturón, cero costo extra.
- **Mock RUNT determinista**: dict de 8 placas demo (incluida `XYZ-987` →
  Chevrolet Spark 2020, tipo auto; al menos 1 moto) + fallback por hash de la placa
  sobre una lista fija de vehículos verosímiles (misma placa → siempre el mismo
  vehículo). Etiquetado "simulado" en docstring y en el campo `fuente` del response.
- **Fasecolda (siniestralidad/salvamento)** se simula dentro del mismo módulo con
  un flag simple en el response del vehículo (`historial: "limpio"`) — suficiente
  para el pitch, sin tool aparte.

## Principios

- Verde por fase: `.venv\Scripts\python.exe -m pytest -q` desde `backend/`.
- Fricción cero honesta: lo "deducido" solo se marca conocido si el dato REALMENTE
  está en el perfil resuelto (nada de fingir que la base sabe lo que no tiene).
- Las simulaciones se etiquetan como tales (código + response), como el handoff.
- Contrato HTTP: solo cambios aditivos (campos opcionales nuevos en el perfil).
- Cero dependencias nuevas, cero env vars nuevas, cero gasto de LLM en tests.

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | backend | Ninguno | 5m | _(sin commit)_ |
| 1 | Matriz de perfilamiento + tool `campos_pendientes` | backend | Aditivo | 40m | `feat(back): add profiling matrix and pending fields tool` |
| 2 | RUNT simulado + tool `consultar_vehiculo` | backend | Aditivo | 35m | `feat(back): add simulated runt lookup for mobility quotes` |

Total estimado: ~80m (estimación del brain: 3h — margen amplio; A3/B4 ya dejaron la
infraestructura de tools y factores).

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: backend
**Objetivo**: baseline verde y confirmación de los puntos de enganche.
**Archivos afectados**: ninguno (solo lectura).
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` (esperado: 463 passed,
   9 skipped).
2. Confirmar el patrón de mock del LLM en `test_orchestrator.py` (cómo se guioniza
   una conversación con tool calls) — se reutiliza en ambas fases.
3. Confirmar los buckets de `debt_balance` en `productos.json` (`<50M`, `50-150M`,
   `>150M`) y `vehicle_type` (`auto`, `moto`) para que los campos nuevos de perfil
   usen EXACTAMENTE esos valores (activan los factores B4 sin tocar el motor).
**Pruebas / verificación**: suite en verde; valores anotados.
**Riesgos**: ninguno.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit — fase de solo lectura)_

---

## Fase 1 — Matriz de perfilamiento + tool `campos_pendientes`

**Proyecto**: backend
**Objetivo**: el agente sabe por categoría qué preguntar y qué NO (fricción cero);
un afiliado en Vida no vuelve a responder edad/género/ocupación (criterio 1) y un
prospecto completa cualquier categoría declarando (criterio 3).
**Archivos afectados**:
`backend/app/services/profiling_matrix.py` (nuevo) ·
[agent_tools.py](backend/app/services/agent_tools.py) ·
[conversation.py (schemas)](backend/app/schemas/conversation.py) ·
[orchestrator.py](backend/app/services/orchestrator.py) ·
[conversation.py (service)](backend/app/services/conversation.py) (setear `source`
al precargar perfil de afiliado) ·
`backend/tests/test_profiling_matrix.py` (nuevo)
**Impacto en contrato API (front↔back)**: No en rutas/status; el shape del perfil en
`ConversationResponse` gana campos opcionales (`source`, `gender`) — aditivo, el
frontend no los usa.
**Acciones**:
1. `ProfileData`: agregar `source: Optional[str]` y `gender: Optional[str]`
   (aditivos). Setear `source="base"` + `gender` en los 3 puntos que resuelven
   perfil desde la base: `_perfilar_cliente` (agent_tools),
   `ConversationService.create` (document_number) y el trigger proactivo de G3;
   `source="declarado"` en el camino declarado.
2. `profiling_matrix.py` (nuevo): `MATRIX` — por categoría del catálogo (`hogar`,
   `vida`, `accidentes`, `movilidad`, `credito`), lista ordenada de campos
   `{campo, pregunta_sugerida, fuente_afiliado: "base"|"preguntar"|"api_simulada",
   atributo_perfil: str | None}` fiel a la Matriz del vault (con los datos sin
   soporte estructurado como solo-pregunta, `atributo_perfil=None`). Función pura
   `campos_pendientes(categoria, profile) -> dict` con `conocidos` (campo, valor si
   hay, fuente legible: "base Colsubsidio (SSO/PILA)" / "declarado" / "RUNT
   simulado") y `pendientes` (en orden, con la pregunta sugerida), aplicando
   fricción cero: fuente base solo cuenta como conocida si `profile.source ==
   "base"` **y** el atributo tiene valor (o es un dato base sin atributo mapeado,
   p. ej. ocupación, que se marca "en la base, no preguntar"); para perfiles
   declarados TODO lo no respondido pasa a pendiente.
3. Tool nueva `campos_pendientes` en `agent_tools.py` (declaración con parámetro
   `categoria` enum de las 5; handler que usa `ctx.profile` — sin perfil →
   `_sin_perfil_error()`; categoría inválida → error controlado) + registro en
   `AGENT_TOOLS`.
4. Orquestador: regla 8 en `SYSTEM_PROMPT` ("antes de pedir un dato consulta
   campos_pendientes de la categoría que estés trabajando; NUNCA preguntes lo que
   figure como conocido — di de dónde lo sabes con naturalidad") y renglón en
   `_build_status_summary`: si hay recomendación vigente, resumen compacto de
   conocidos/pendientes de esa categoría.
5. Tests (TDD-light) en `test_profiling_matrix.py`:
   - **Criterio 1**: perfil afiliado (source="base", con age_range/gender) en
     `vida` → `pendientes` NO contiene edad/género/ocupación y `conocidos` los
     lista con fuente base; con LLM mockeado (patrón test_orchestrator), una
     conversación de vida a un afiliado: el turno del bot tras `campos_pendientes`
     no pregunta edad (assert sobre el guion mockeado y sobre qué tool calls se
     hicieron).
   - **Criterio 3**: perfil declarado (`source="declarado"`) → cada una de las 5
     categorías devuelve pendientes que cubren todos sus campos requeridos (la vía
     no afiliado convierte base→preguntar) y con las respuestas declaradas los
     pendientes se vacían.
   - Tool: categoría inválida → dict de error (nunca excepción); sin perfil →
     error de perfil.
   - `tool_declarations()` incluye la tool nueva (conteo y nombre).
**Pruebas / verificación**: pytest verde (los tests existentes de
`test_agent_tools.py`/`test_orchestrator.py` no cambian: la tool es aditiva y el
system prompt crece sin romper asserts — verificar los que hacen match de texto).
**Riesgos**: tests existentes que asertan el número exacto de tools o fragmentos
del SYSTEM_PROMPT — se actualizan al valor nuevo (aditivo, sin debilitar);
`model_dump(exclude_none=True)` en `_build_status_summary` mantiene el prompt
compacto aunque ProfileData crezca.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `feat(back): add profiling matrix and pending fields tool`

---

## Fase 2 — RUNT simulado + tool `consultar_vehiculo`

**Proyecto**: backend
**Objetivo**: la placa dispara la consulta simulada RUNT/Fasecolda y el bot cita
"Chevrolet Spark 2020" antes de cotizar (criterio 2); el tipo de vehículo activa el
factor B4 de movilidad que estaba neutro.
**Archivos afectados**:
`backend/app/services/integrations/runt.py` (nuevo) ·
[agent_tools.py](backend/app/services/agent_tools.py) ·
[conversation.py (schemas)](backend/app/schemas/conversation.py) (campos vehículo) ·
[profiling_matrix.py](backend/app/services/profiling_matrix.py) (marcar los campos
RUNT como `api_simulada` resuelta) ·
`backend/tests/test_runt_simulado.py` (nuevo)
**Impacto en contrato API (front↔back)**: No en rutas; el perfil gana campos
opcionales de vehículo (aditivo). La cotización de movilidad puede cambiar de monto
para perfiles con moto (factor 0.65 del catálogo por fin alcanzable — intención de
B2/B4).
**Acciones**:
1. `integrations/runt.py` (nuevo, docstring en español etiquetando la simulación —
   "aquí entra el RUNT/Fasecolda real; deuda documentada como el handoff"):
   `consultar_vehiculo(placa) -> dict` — normaliza la placa (mayúsculas, sin
   guiones/espacios), busca en `_PLACAS_DEMO` (8 entradas verosímiles; `XYZ987` →
   `{marca: "Chevrolet", linea: "Spark", modelo: 2020, tipo: "auto", cilindraje:
   1200}`; incluir ≥1 moto) y si no está, fallback determinista: hash de la placa →
   índice sobre una lista fija de vehículos (misma placa, mismo vehículo, siempre).
   Response siempre con `fuente: "RUNT simulado"` e `historial: "limpio"`
   (Fasecolda simulado). Placa vacía/invalida → `{"error": ...}` controlado.
2. `ProfileData`: campos aditivos `vehicle_plate`, `vehicle_brand`, `vehicle_line`,
   `vehicle_year`, `vehicle_type` ("auto"|"moto" — EXACTO al bucket del factor B4),
   `vehicle_use`, `debt_balance` (buckets B4; lo llena la conversación de crédito
   vía `perfilar_cliente`/declaración — el campo existe para que el factor deje de
   ser neutro cuando el cliente lo declare).
3. Tool nueva `consultar_vehiculo` en `agent_tools.py`: declaración (parámetro
   `placa` requerido; descripción: llamarla apenas el cliente dé la placa en
   movilidad, citar marca/línea/año al cliente); handler que llama al módulo RUNT,
   escribe los campos de vehículo en `ctx.profile` (creándolo declarado si no
   existe aún) y devuelve el vehículo + `fuente` para que el LLM lo cite. Registro
   en `AGENT_TOOLS`. Agregar `debt_balance`/`vehicle_use` como parámetros opcionales
   de `perfilar_cliente` (vía declarada).
4. `profiling_matrix.py`: en movilidad, los campos marca/línea/modelo pasan a
   `conocidos` con fuente "RUNT simulado" cuando `vehicle_brand` ya está en el
   perfil; la placa es el único pendiente inicial de esa vía.
5. Tests (TDD-light) en `test_runt_simulado.py`:
   - **Criterio 2**: `consultar_vehiculo("XYZ-987")` → Chevrolet Spark 2020, tipo
     auto, `fuente: "RUNT simulado"`; conversación movilidad con LLM mockeado: tras
     dar la placa, el resultado de la tool queda en `ctx.profile` y el guion del
     bot cita "Chevrolet Spark 2020" ANTES del tool call `cotizar` (assert sobre el
     orden de llamadas del guion mockeado).
   - Determinismo del fallback: placa desconocida dos veces → mismo vehículo;
     placas distintas pueden diferir; normalización (`xyz-987` == `XYZ987`).
   - Factor activo: cotización de `movilidad-auto` con `vehicle_type="moto"` es
     0.65× la de `"auto"` (el factor B4 deja de ser neutro).
   - Negativos: placa vacía → error controlado (nunca excepción al LLM);
     `campos_pendientes("movilidad", perfil_con_vehiculo)` ya no lista
     marca/modelo.
**Pruebas / verificación**: pytest completo verde; manual opcional (gasta cuota):
conversación real de movilidad con la placa demo. Anotar como pendiente manual.
**Riesgos**: ninguno estructural — todo aditivo; los guardrails de precios
(`_guard_reply`) no se tocan (el vehículo no es cifra monetaria).

🛑 **CHECKPOINT FINAL** — B5 cumple sus 3 criterios (fricción cero en vida para
afiliados, placa demo citada desde el RUNT simulado, prospecto completa declarando).
Marcar B5 en el brain — Feature B completa. Deuda documentada: RUNT/Fasecolda
reales.
**Commit sugerido**: `feat(back): add simulated runt lookup for mobility quotes`
