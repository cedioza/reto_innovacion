# Plan — D1: UI base del chat estilo mensajería · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-25 · **Tipo**: plan de implementación por fases.
> **Base**: (ninguno) — primer plan de la Feature D (Chat web) en este repo.
> **Proyectos afectados**: frontend.
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

Convertir [ChatView.vue](frontend/src/features/chat/ChatView.vue) de placeholder
("Backend: ✅ conectado") a una interfaz de chat con estética de mensajería
(WhatsApp-like): burbujas, indicador de "escribiendo…", timestamps, scroll correcto,
input fijo abajo, mobile-first. Es la tarea **D1** de la Feature "Chat web" del vault
(`colsubsidio-brain/07 - Tareas/Feature D - Chat web/D1 - UI base del chat estilo
mensajeria.md`) y es la cara del entregable: el jurado evalúa la solución **entrando a
este link y usándolo**, sin explicación del equipo.

Esta fase trabaja **100% con mensajes mock** (sin backend real) — D2 conecta esta UI
al orquestador (`POST /conversations/{id}/message`, A3) después.

## Contexto / hallazgos del análisis

**Del vault** (fuera de este repo, en `colsubsidio-brain/`, referenciado como ruta de
texto porque no es resoluble como link relativo desde la raíz de este repo):
- `07 - Tareas/Feature D - Chat web/D1 - UI base del chat estilo mensajeria.md` —
  tarea origen: `capa: front`, sin dependencias, bloquea a D2, estimación 4h.
- **Enunciado del reto**: "la experiencia transmite confianza y cercanía" es criterio
  explícito de evaluación; "no negociable" que la experiencia inspire confianza (la
  gente le teme a los seguros porque no los entiende).
- **Charla "Gana el mejor pitch"**: se nota de inmediato una interfaz "generada por IA
  sin criterio" y resta puntos — cada elemento de la UI debe tener un porqué, sin
  clonar la marca Colsubsidio pixel a pixel.
- **Reglas y entregables**: el demo debe ser navegable por el jurado **sin
  intervención del equipo** — refuerza que el flujo de mensajería debe ser intuitivo
  por sí solo (sin tutorial, sin texto de ayuda adicional).
- D1 "bloquea_a: [D2]" — D2 depende de D1 + A3 y reutiliza el estado de conversación
  que D1 deja preparado (composable/store) para conectarlo al backend real.

**Del código actual:**
- [ChatView.vue](frontend/src/features/chat/ChatView.vue#L1) es un placeholder de 25
  líneas: solo hace `getHealth()` y muestra un texto de estado. No hay componentes de
  chat, ni estado de conversación, ni estilos propios más allá de los globales de
  [App.vue](frontend/src/App.vue#L17).
- [router/index.js](frontend/src/router/index.js#L8) ya registra `ChatView` en `/` —
  no hace falta tocar el router.
- [frontend/CLAUDE.md](frontend/CLAUDE.md) fija dos reglas relevantes:
  - Componentes NUNCA hacen `fetch` directo (no aplica todavía: D1 es 100% mock, no
    hay llamadas HTTP nuevas).
  - "Estado que solo usa una feature puede vivir como composable dentro de la
    feature" — el estado de conversación hoy **solo lo usa `chat`**, así que este plan
    lo modela como **composable** (`features/chat/composables/useChat.js`), no como
    store global de Pinia. Si D2 necesita compartirlo entre features (p. ej. un
    badge de "conversación activa" en la navbar), se promueve a `src/stores/` en ese
    momento — no antes.
- [package.json](frontend/package.json#L11) ya trae `vue`, `vue-router`, `pinia` — sin
  ninguna librería de UI. **No se necesita ninguna dependencia nueva**: el criterio de
  aceptación de D1 lo exige explícitamente ("sin dependencias UI pesadas nuevas").
- `frontend/node_modules` **no existe todavía** en este entorno — hace falta
  `npm install` (de lo ya declarado en `package.json`, no agrega paquetes nuevos)
  antes de poder correr `npm run build` o `npm run dev`.
- [index.html](frontend/index.html#L5) ya trae `viewport width=device-width` — el
  mobile-first no necesita tocar esto.
- No hay test runner configurado en el frontend (no hay `vitest` ni carpeta `tests/`)
  — la verificación de cada fase es `npm run build` + revisión manual en navegador
  (desktop y con devtools en modo móvil), tal como indica el criterio de aceptación de
  D1 ("se ve fluida en desktop y móvil").
- No hay planes previos sobre Feature D en `.claude/analysis/plans/` — este es el
  primero.

## Decisiones pendientes (bloqueantes)

(ninguna) — el alcance de D1 es autocontenido (mock only) y no depende de ninguna
decisión de producto o técnica abierta. La paleta "verde institucional sobrio" que
pide D1 no está documentada en el vault con un hex exacto; este plan usa un verde
sobrio de referencia (`#00754A` aprox., inspirado en la identidad pública de
Colsubsidio) como valor por defecto en variables CSS — es fácil de ajustar después y
no bloquea el desarrollo.

## Principios

- Verde por fase: cada fase deja `npm run build` OK y el servidor de desarrollo
  (`npm run dev`) levantando sin errores en consola.
- Proyecto único (frontend) en las 4 fases — no hay contraparte de backend que
  actualizar en este plan.
- Aditivo antes que destructivo: el composable y los componentes de presentación se
  crean primero, sin tocar `ChatView.vue`; el reemplazo del placeholder (que sí borra
  código existente) es la última fase de código.
- Alcance mínimo: solo lo que pide D1 (mock, estética, responsive). Nada de conexión a
  backend real (eso es D2), nada de tarjetas de recomendación/cotización (D3), nada de
  nota de voz (D5).
- Sin dependencias nuevas — CSS propio con variables, sin librería de componentes.

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | frontend | Ninguno | 5m | _(sin commit)_ |
| 1 | Estado de conversación mock (composable) | frontend | Aditivo | 45m | `feat(front): add useChat composable with mock conversation state` |
| 2 | Componentes de presentación del chat | frontend | Aditivo | 1h 15m | `feat(front): add MessageBubble, TypingIndicator and ChatInput components` |
| 3 | Integración en ChatView + layout mensajería responsive | frontend | Medio | 1h 30m | `feat(front): replace chat placeholder with messaging-style UI` |
| 4 | Pulido responsive y verificación cross-viewport | frontend | Aditivo | 30m | `style(front): polish chat responsive layout for mobile` |

**Total estimado**: ~4h — coincide con la estimación original de D1 en el vault.

---

## Fase 0 — Pre-flight (read-only)
**Proyecto**: frontend
**Objetivo**: confirmar el estado real del entorno antes de tocar código.
**Archivos afectados**: ninguno (solo lectura).
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Verificar que `frontend/node_modules` no existe (confirmado en el análisis) — se
   necesitará `npm install` como primer paso de la Fase 1.
2. Confirmar que no hay cambios sin commitear en `frontend/` (`git status`).
3. Confirmar que `frontend/src/features/chat/ChatView.vue` sigue siendo el placeholder
   descrito (no fue tocado por otro trabajo en paralelo).

**Pruebas / verificación**: solo lectura, sin comandos de build todavía (no hay
`node_modules`).
**Riesgos**: ninguno.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit — fase read-only)_

---

## Fase 1 — Estado de conversación mock (composable)
**Proyecto**: frontend
**Objetivo**: preparar el estado reactivo de la conversación (mensajes, indicador de
"escribiendo") con datos hardcodeados, aislado de la UI, para que D2 pueda
reemplazar la lógica interna por llamadas reales sin tocar los componentes visuales.
**Archivos afectados**:
- `frontend/node_modules` (generado por `npm install`, no versionado).
- `frontend/src/features/chat/composables/useChat.js` (nuevo).
**Impacto en contrato API (front↔back)**: No — cero llamadas HTTP en esta fase.
**Acciones**:
1. `npm install` en `frontend/` (instala lo ya declarado en `package.json`; no agrega
   dependencias nuevas).
2. Crear `useChat.js` con:
   - `messages`: `ref` de objetos `{ id, from: 'user' | 'bot', text, timestamp }`,
     sembrado con 2-3 mensajes mock (saludo del asistente + una respuesta de ejemplo)
     para que la conversación no arranque vacía.
   - `isTyping`: `ref(false)`.
   - `sendMessage(text)`: agrega el mensaje del usuario, activa `isTyping`, simula
     latencia con `setTimeout` (900–1500ms), agrega una respuesta mock del bot y
     desactiva `isTyping`.
   - Expone `{ messages, isTyping, sendMessage }` vía `export function useChat()`.
3. No importar ni usar este composable todavía desde `ChatView.vue` (eso es Fase 3) —
   se deja listo y aislado.

**Pruebas / verificación**: `npm run build` debe pasar (el composable no usado no
rompe el build de Vite). Revisión manual del archivo: sin `fetch`/`api.js` importado
(D1 es 100% mock).
**Riesgos**: ninguno — código nuevo sin efectos colaterales.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `feat(front): add useChat composable with mock conversation state`

---

## Fase 2 — Componentes de presentación del chat
**Proyecto**: frontend
**Objetivo**: construir los tres componentes visuales que pide D1, reutilizables y
sin lógica de negocio (reciben props, emiten eventos).
**Archivos afectados**:
- `frontend/src/features/chat/components/MessageBubble.vue` (nuevo).
- `frontend/src/features/chat/components/TypingIndicator.vue` (nuevo).
- `frontend/src/features/chat/components/ChatInput.vue` (nuevo).
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. `MessageBubble.vue` — prop `message` (`{ from, text, timestamp }`); burbuja
   alineada a la derecha (usuario) o izquierda (asistente, con avatar/inicial),
   timestamp en formato corto (`HH:mm`), color de fondo distinto por `from` usando
   variables CSS del verde institucional sobrio.
2. `TypingIndicator.vue` — sin props, tres puntos animados (CSS puro, `@keyframes`),
   estética consistente con `MessageBubble` del lado del asistente.
3. `ChatInput.vue` — `v-model` interno o prop/emit controlado, emite `send` con el
   texto al presionar Enter o el botón; input fijo con buen tamaño táctil (mobile);
   deshabilitado mientras `isTyping` (prop) para evitar mensajes en tropel.
4. Estilos: `<style scoped>` en cada componente; definir las variables de color
   (verde institucional, grises de fondo) una sola vez, en un bloque `:root` dentro de
   `MessageBubble.vue` o, si se repiten en los 3 componentes, extraerlas a
   `frontend/src/features/chat/chat-theme.css` e importarlas donde haga falta —
   decidir al implementar según cuánto se repitan.

**Pruebas / verificación**: `npm run build` debe pasar (componentes no importados
aún no rompen el build). Revisión visual rápida montando cada componente de forma
temporal en `ChatView.vue` es opcional aquí — la integración real y su verificación
visual completa ocurre en la Fase 3.
**Riesgos**: ninguno — componentes aislados, sin uso todavía.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 3 sin aprobación del usuario.
**Commit sugerido**: `feat(front): add MessageBubble, TypingIndicator and ChatInput components`

---

## Fase 3 — Integración en ChatView + layout mensajería responsive
**Proyecto**: frontend
**Objetivo**: reemplazar el placeholder por la vista de chat real (mock), cumpliendo
los tres criterios de aceptación de D1.
**Archivos afectados**:
- `frontend/src/features/chat/ChatView.vue` (reescritura completa).
**Impacto en contrato API (front↔back)**: No — se elimina el único uso de
`getHealth()` que tenía el placeholder (era un smoke check, no parte de los criterios
de D1). D2 introducirá el estado de conexión real cuando conecte al backend; no se
pierde nada porque el mock no depende de la disponibilidad del backend.
**Acciones**:
1. Reescribir `ChatView.vue`: importar `useChat()`, `MessageBubble`, `TypingIndicator`,
   `ChatInput`.
2. Layout: contenedor de altura completa (`100dvh` o equivalente), lista de mensajes
   con `overflow-y: auto`, `ChatInput` fijo al fondo (`position: sticky` o flex con
   `flex-shrink: 0`), header simple con nombre/avatar del asistente ("Asistente
   Colsubsidio" o similar, sobrio, sin clonar la marca).
3. Auto-scroll: al agregar un mensaje (usuario o bot) o al activarse `isTyping`,
   hacer scroll al fondo del contenedor de mensajes (`watch` sobre `messages`/
   `isTyping` + `scrollTop = scrollHeight` vía `template ref`, o `scrollIntoView` en
   un elemento ancla al final de la lista).
4. Conectar `ChatInput` → `sendMessage(text)` del composable; mostrar
   `TypingIndicator` cuando `isTyping === true`.
5. Mobile-first: diseñar primero para ancho de teléfono (~375px) y expandir con
   `max-width` centrado en desktop (p. ej. `max-width: 480px` o `640px` simulando un
   panel de chat, no un layout de escritorio ancho).

**Pruebas / verificación**:
- `npm run build` debe pasar.
- `npm run dev` y revisión manual en navegador: enviar un mensaje mock, ver que
  aparece de inmediato, que el `TypingIndicator` aparece durante la simulación de
  latencia, y que la respuesta del bot aparece después con scroll automático al
  fondo.
- Revisión con devtools en modo responsive (~375×667, iPhone SE/12 mini) para
  confirmar que el input queda visible y usable, sin overflow horizontal.
**Riesgos**: el auto-scroll y el `100dvh` son los puntos más propensos a bugs visuales
(algunos navegadores móviles manejan `dvh`/barra de direcciones distinto) — si da
problemas, usar `100vh` con fallback y probar en el dispositivo real del jurado si es
posible antes del cierre del hackathon.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 4 sin aprobación del usuario.
**Commit sugerido**: `feat(front): replace chat placeholder with messaging-style UI`

---

## Fase 4 — Pulido responsive y verificación cross-viewport
**Proyecto**: frontend
**Objetivo**: cerrar los criterios de aceptación de D1 con una pasada de pulido y
verificación explícita en varios anchos, ya que "el jurado puede abrir desde el
celular" y "se nota la interfaz generada por IA sin criterio".
**Archivos afectados**:
- `frontend/src/features/chat/ChatView.vue` y/o los componentes de
  `frontend/src/features/chat/components/` (ajustes puntuales, sin archivos nuevos).
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Revisar espaciados, tamaños táctiles (mínimo ~44px de alto en el input/botón de
   enviar) y contraste de color en las burbujas (accesibilidad básica).
2. Probar en al menos 3 anchos: móvil (~375px), tablet (~768px), desktop (~1280px) —
   ajustar `max-width`/paddings si algo se ve roto o desproporcionado.
3. Verificar que no quedó ningún rastro del placeholder anterior (texto de "Backend:
   conectado", imports de `getHealth` sin usar) — limpieza final.
4. Revisar el checklist de criterios de aceptación de D1 uno por uno antes de cerrar.

**Pruebas / verificación**: `npm run build`; recorrido manual del checklist de D1:
- [ ] Conversación simulada se ve fluida en desktop y móvil.
- [ ] El typing indicator aparece mientras "responde el bot".
- [ ] Sin dependencias UI pesadas nuevas (confirmar `package.json` sin diffs de
  dependencias).

**Riesgos**: ninguno — fase de pulido, bajo riesgo de romper algo ya funcional.

🛑 **CHECKPOINT** — Detente aquí. Esto cierra D1. La siguiente tarea del vault es D2
(Chat conectado al orquestador), que depende de D1 **y** de A3 (endpoint del
orquestador en backend) — no iniciar D2 hasta confirmar que A3 existe o decidir
conectar temporalmente contra endpoints estructurados existentes (nota del propio D2
en el vault).
**Commit sugerido**: `style(front): polish chat responsive layout for mobile`
