# Plan — A1: Cliente Gemini con function calling · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-24 · **Tipo**: plan de implementación por fases.
> **Base**: [20260723-health-terceros-backend.plan.md](.claude/analysis/plans/20260723-health-terceros-backend.plan.md)
> (estableció el patrón de cliente REST con httpx sin SDK, config vía `Settings`,
> tests con mocks sin red). Insumo externo: tarea **A1** del brain
> (`colsubsidio-brain/07 - Tareas/Feature A - Agente conversacional/A1 - Cliente Gemini
> con function calling.md`) y sus notas relacionadas (`04 - Tecnología/Stack y
> arquitectura.md`, `02 - Idea y Negocio/Alcance MVP.md`).
> **Proyectos afectados**: backend.
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

Crear `backend/app/services/integrations/gemini_client.py`: el módulo que envía un
**historial de mensajes + definiciones de herramientas** a Gemini y devuelve la
respuesta parseada (**texto o tool call**), con **entrada de audio** (multimodal,
notas de voz OGG/Opus) y **timeout + 1 reintento + fallback controlado** (si Gemini
cae, un mensaje de disculpa — jamás una excepción hacia arriba).

Es el "cerebro conversacional" de la arquitectura del brain: A1 **bloquea** A3
(orquestador LLM), D5 y F2, pero se implementa **sin acoplarse a ningún servicio de
negocio** — las tools reales y su ejecución son A2/A3. Hoy lo único que existe de
Gemini es el ping del health check.

## Contexto / hallazgos del análisis

**De la tarea A1 y el vault** (leídos completos):

- Modelo: `gemini-2.5-flash` — el mismo del health check
  ([gemini.py:14](backend/app/services/integrations/gemini.py#L14)).
- El wrapper es sobre `generateContent` con `tools` (function declarations),
  historial de `contents` y `systemInstruction`.
- Audio: partes `inline_data` (OGG/Opus base64) — Gemini multimodal entiende el audio
  directo, **sin pipeline STT aparte** (`Stack y arquitectura`, "Voz nivel 1"). La
  descarga del media del webhook NO es de A1 (es de la feature F de canales).
- `GEMINI_API_KEY` ya está configurada (en `.env` local y en `Settings`) — cero setup.
- Regla de oro del brain: datos de productos/precios jamás salen del LLM libre — por
  eso el cliente devuelve tool calls parseadas para que el orquestador (A3) ejecute
  motores deterministas; el cliente NO ejecuta herramientas.
- "Flujo feliz impecable > manejo exhaustivo de errores" (`Deuda técnica aceptada`),
  pero A1 exige explícitamente el fallback controlado — es parte de sus criterios.

**Del código del repo** (leído completo):

- [gemini.py](backend/app/services/integrations/gemini.py) — patrón a seguir: httpx
  sin SDK, header `x-goog-api-key`, nunca lanza excepción, key jamás en mensajes de
  error. Se queda intacto (health check); `gemini_client.py` es módulo nuevo aparte.
  Ambos comparten modelo y endpoint — el cliente define sus propias constantes (el
  health check no se toca; unificarlas sería refactor fuera de alcance).
- [config.py](backend/app/core/config.py) — `gemini_api_key` ya existe. **No hay env
  vars nuevas** (el modelo va como constante: mismo criterio que el health check).
- El registro `INTEGRATIONS` de
  [integrations/\_\_init\_\_.py](backend/app/services/integrations/__init__.py) es
  solo para health checks — `gemini_client` **no** se registra ahí.
- Patrón de tests con mock de httpx vía monkeypatch ya establecido en
  [test_integrations_health.py](backend/tests/test_integrations_health.py) — se reusa.
- `httpx` ya es dependencia runtime; **cero dependencias nuevas**.
- Capas: es lógica de integración → `app/services/integrations/` (regla del plan de
  health checks). Los tipos del resultado son dataclasses del propio módulo (no van
  en `app/schemas/` — no son DTOs HTTP; precedente: dataclass `Integration` en
  `integrations/__init__.py`).
- Suite actual: **123 tests en verde** — línea base de la Fase 0.

**Diseño de la interfaz del módulo** (funcional, como los demás clientes del repo —
`send_whatsapp_message`, `send_telegram_message`):

```python
@dataclass
class GeminiReply:
    kind: Literal["text", "tool_call", "error"]
    text: str = ""              # kind=text → respuesta; kind=error → mensaje de disculpa
    tool_name: str = ""         # kind=tool_call
    tool_args: dict = field(default_factory=dict)

def generate_reply(
    contents: list[dict],                 # historial en formato Gemini (role/parts)
    *,
    tools: list[dict] | None = None,      # function declarations
    system_instruction: str | None = None,
) -> GeminiReply: ...

def text_part(text: str) -> dict: ...
def audio_part(data: bytes, mime_type: str = "audio/ogg") -> dict: ...
def user_message(*parts: dict) -> dict: ...
def model_message(*parts: dict) -> dict: ...
```

Comportamiento de errores: timeout ~30 s por intento; **1 reintento** solo ante
`httpx.HTTPError` o status 5xx (un 4xx no se reintenta: key inválida/payload malo no
mejoran reintentando); agotado el reintento → `GeminiReply(kind="error",
text=<disculpa en español>)`. Sin key → mismo camino de error controlado. La API key
y la URL jamás aparecen en logs ni en `text`.

## Decisiones pendientes (bloqueantes)

(ninguna — las de diseño quedaron resueltas arriba: interfaz funcional con
`GeminiReply`, constantes en el módulo, sin env vars nuevas, sin registro en
`INTEGRATIONS`. Nota no bloqueante: la verificación live de la Fase 4 gasta unas
pocas llamadas de los créditos del kit.)

## Principios

- Verde por fase: `pytest` del backend en verde al cierre de cada fase (línea base 123).
- **Tests sin red**: todos los criterios de aceptación de A1 se cubren con mocks de
  httpx (monkeypatch); la verificación contra Gemini real es la Fase 4 (manual/gated).
- **Sin acoplar al negocio**: `gemini_client.py` no importa services de negocio ni
  ejecuta tools — devuelve la tool call parseada y ya (fronteras con A2/A3).
- Aditivo puro: no se toca el health check ni ningún módulo existente.
- Config solo por env vars ya existentes (`GEMINI_API_KEY`); cero dependencias nuevas.
- Contrato HTTP front↔back: **ninguna fase lo toca** (módulo interno, sin endpoints).

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | backend | Ninguno | 5m | _(sin commit)_ |
| 1 | Cliente base: texto + reintento + fallback | backend | Aditivo | 30m | `feat(back): add gemini client with retry and fallback` |
| 2 | Function calling (tools + parseo de tool call) | backend | Aditivo | 25m | `feat(back): support function calling in gemini client` |
| 3 | Entrada de audio multimodal (notas de voz) | backend | Aditivo | 20m | `feat(back): accept audio parts in gemini client` |
| 4 | Verificación live contra Gemini real (gated) | backend | Aditivo | 15m | `test(back): add gated live checks for gemini client` |

Total: ~1h35m. Si el tiempo aprieta: la Fase 4 es recortable (la verificación live
puede hacerse a mano desde una consola); la Fase 3 es recortable solo si se acepta
aplazar las notas de voz (el MVP las lista, pero el propio Alcance MVP dice "si el
tiempo aprieta, se recorta sin romper nada").

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: backend
**Objetivo**: confirmar punto de partida verde.
**Archivos afectados**: ninguno.
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` → **123 en verde**.
2. Confirmar que `GEMINI_API_KEY` tiene valor en `backend/.env` (para la Fase 4).
3. Confirmar que el health check de Gemini responde (opcional, gasta 1 llamada):
   `curl -X POST http://localhost:8000/health/integrations/gemini` → 200.

**Pruebas / verificación**: las de arriba.
**Riesgos**: ninguno.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit)_

---

## Fase 1 — Cliente base: texto + reintento + fallback

**Proyecto**: backend
**Objetivo**: `generate_reply()` funcionando para conversación de texto: historial
`contents` + `systemInstruction`, timeout, 1 reintento y fallback controlado.
**Archivos afectados**:
- `backend/app/services/integrations/gemini_client.py` — **nuevo**: constantes
  (`GEMINI_MODEL = "gemini-2.5-flash"`, URL de `generateContent`, timeout, mensaje de
  disculpa), dataclass `GeminiReply`, helpers `text_part`/`user_message`/
  `model_message`, y `generate_reply(contents, *, tools=None, system_instruction=None)`
  (en esta fase `tools` se acepta pero aún no se parsea la tool call — llega en Fase 2).
- `backend/tests/test_gemini_client.py` — **nuevo**.

**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Implementar el request builder: payload `{contents, systemInstruction?,
   generationConfig}` con header `x-goog-api-key` (mismo estilo del health check).
2. Parseo de respuesta de texto: `candidates[0].content.parts[*].text` concatenado →
   `GeminiReply(kind="text")`.
3. Manejo de errores: sin key → `kind="error"`; `httpx.HTTPError` o 5xx → **1
   reintento**; si persiste → `kind="error"` con el mensaje de disculpa (constante en
   español, p. ej. "Lo siento, tuve un problema técnico. ¿Intentamos de nuevo?"); 4xx
   → `kind="error"` sin reintento. La key/URL jamás en el texto del error.
4. Tests (mock httpx, patrón de `test_integrations_health.py`): "hola" → texto;
   error de red 2 veces → `kind="error"` + mensaje de disculpa, sin excepción;
   falla 1 vez + éxito al reintento → texto; 401 → error sin reintento (assert de
   que solo hubo 1 llamada); sin key → error sin llamada HTTP.

**Pruebas / verificación**: `.venv\Scripts\python.exe -m pytest -q` verde.
**Riesgos**: ninguno (módulo aislado).

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `feat(back): add gemini client with retry and fallback`

---

## Fase 2 — Function calling (tools + parseo de tool call)

**Proyecto**: backend
**Objetivo**: el cliente envía `tools` (function declarations) y, si Gemini responde
con una llamada a herramienta, la devuelve **parseada** (`tool_name` + `tool_args`)
— criterio de aceptación central de A1.
**Archivos afectados**:
- [gemini_client.py](backend/app/services/integrations/gemini_client.py) — incluir
  `tools` en el payload (`[{"functionDeclarations": [...]}]`) y detectar
  `candidates[0].content.parts[*].functionCall` → `GeminiReply(kind="tool_call",
  tool_name=..., tool_args=...)`. Prioridad: si hay functionCall, gana sobre el texto.
- [test_gemini_client.py](backend/tests/test_gemini_client.py) — ampliar.

**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Payload con `tools` cuando se pasan declarations (formato Gemini REST:
   `functionDeclarations` con name/description/parameters JSON-schema).
2. Parseo de `functionCall {name, args}` → `kind="tool_call"`.
3. Tests con mock: respuesta con functionCall (simulando el prompt "cotiza X" del
   criterio de A1) → `tool_name`/`tool_args` correctos; respuesta con texto y tool
   declarada → `kind="text"`; functionCall con `args` ausente → `tool_args == {}`
   (nunca KeyError).

**Pruebas / verificación**: pytest verde; los args llegan como dict listos para que
A3 los despache (sin ejecutar nada aquí).
**Riesgos**: el formato de functionCall varía sutilmente entre versiones de la API →
el parseo es defensivo (`.get()` en cada nivel) y la Fase 4 lo valida contra la API
real.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 3 sin aprobación del usuario.
**Commit sugerido**: `feat(back): support function calling in gemini client`

---

## Fase 3 — Entrada de audio multimodal (notas de voz)

**Proyecto**: backend
**Objetivo**: poder incluir un audio (OGG/Opus u otro mime) como parte del mensaje —
la base de "entender notas de voz" del MVP. La descarga del media del webhook NO va
aquí (feature F de canales); A1 solo acepta los bytes.
**Archivos afectados**:
- [gemini_client.py](backend/app/services/integrations/gemini_client.py) — helper
  `audio_part(data: bytes, mime_type="audio/ogg")` que construye
  `{"inline_data": {"mime_type": ..., "data": <base64>}}`; `generate_reply` no
  cambia (las parts son opacas para él).
- [test_gemini_client.py](backend/tests/test_gemini_client.py) — ampliar.

**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Implementar `audio_part` (base64 estándar, `import base64`).
2. Tests: un mensaje con `audio_part(b"...bytes...")` + `text_part("¿qué dice el
   audio?")` produce un payload cuyo `inline_data.data` es el base64 correcto y cuyo
   mime es `audio/ogg`; la respuesta mockeada (transcripción) llega como
   `kind="text"` — cubre el criterio "un audio corto devuelve su
   transcripción/interpretación" (con mock; el real es Fase 4).

**Pruebas / verificación**: pytest verde.
**Riesgos**: audios grandes inflan el payload base64 — para notas de voz de WhatsApp
(≤ ~1 min) es irrelevante; si creciera, la Files API de Gemini sería otra tarea.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 4 sin aprobación del usuario.
**Commit sugerido**: `feat(back): accept audio parts in gemini client`

---

## Fase 4 — Verificación live contra Gemini real (gated)

**Proyecto**: backend
**Objetivo**: validar los 4 criterios de aceptación de A1 contra la API real (los
mocks no prueban que el formato del payload sea el que Gemini espera). Gasta unas
pocas llamadas de los créditos del kit.
**Archivos afectados**:
- [test_gemini_client.py](backend/tests/test_gemini_client.py) o archivo aparte
  `backend/tests/test_gemini_client_live.py` — tests **gated**: se saltan salvo que
  `RUN_LIVE_GEMINI_TESTS=1` esté en el entorno (`pytest.mark.skipif`), para que la
  suite normal siga sin red y sin gastar créditos.

**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Test live 1: "hola" con una tool declarada → `kind="text"` con texto no vacío.
2. Test live 2: prompt que fuerza tool call ("cotiza un seguro de hogar...", con la
   declaration de `cotizar`) → `kind="tool_call"` con nombre y args.
3. Test live 3: audio corto de prueba (generar un OGG mínimo o usar un fixture
   pequeño en `tests/fixtures/`) → respuesta de texto con su interpretación.
4. Correr: `RUN_LIVE_GEMINI_TESTS=1` + pytest de ese archivo, con la key del `.env`.
5. Ajustar el parseo si la API real difiere del mock (aquí se pagan las sorpresas,
   no en A3).

**Pruebas / verificación**: suite normal verde (los live se saltan sin la env var);
corrida live manual verde con la key real.
**Riesgos**: red/cuota del evento; si el fixture de audio complica, el criterio se
verifica a mano desde una consola Python y la fase se cierra sin el test 3.

🛑 **CHECKPOINT** — fin del plan.
**Commit sugerido**: `test(back): add gated live checks for gemini client`
