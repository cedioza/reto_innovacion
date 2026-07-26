# Plan — C3 brecha criterio 2: timestamp por mensaje en el historial · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-25 · **Tipo**: plan de implementación por fases.
> **Base**: [20260725-c3-conversaciones-solicitudes-postgres.plan.md](.claude/analysis/plans/20260725-c3-conversaciones-solicitudes-postgres.plan.md)
> (C3 ejecutado y mergeado — este plan cierra la brecha del veredicto: criterio 2
> "historial completo (rol, contenido, **timestamp**) consultable por conversación"
> quedó parcial porque `Message` no tiene timestamp propio).
> **Proyectos afectados**: ambos (backend primero; frontend consume después).
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

Cada mensaje de la transcripción lleva su propio timestamp (ISO-8601 UTC) generado al
crearse y persistido con la conversación. Con eso la transcripción puede decir *cuándo*
se dijo cada cosa — lo que el panel (G1/G2) y el argumento de "asesoría trazable"
necesitan mostrar — y el chat web pinta la hora real del servidor al rehidratar en vez
de perderla.

## Contexto / hallazgos del análisis

**Backend — el schema y sus 13 puntos de creación:**

- [Message](backend/app/schemas/conversation.py#L16-L20) tiene `role`, `content`,
  `type`, `payload` — sin timestamp. La conversación solo tiene `created_at` /
  `updated_at` a nivel de registro ([ConversationRecord](backend/app/models/conversation.py)).
- `Message(...)` se instancia en 13 sitios: 6 en
  [conversation.py](backend/app/services/conversation.py) (líneas 119, 145, 155, 225,
  228, 305), 6 en [orchestrator.py](backend/app/services/orchestrator.py) (428, 429 y
  las 4 tarjetas de `_append_card_messages` — 463, 483, 502, 516) y el schema mismo.
  **Con `default_factory` en el campo, ninguno necesita tocarse**: todo mensaje nuevo
  queda sellado al crearse.
- La persistencia C3 guarda `session.model_dump(mode="json")` completo en la columna
  `data` ([conversations.py](backend/app/repositories/conversations.py)) y reconstruye
  con `model_validate` — el campo nuevo viaja y persiste solo, sin tocar repos ni
  modelos SQLModel.
- `_contents_from_history` ([orchestrator.py:113](backend/app/services/orchestrator.py#L113))
  solo lee `role`/`content` — el LLM no ve el campo nuevo; sin impacto.

**Compatibilidad con datos ya persistidos:** las conversaciones guardadas antes del
cambio no traen `timestamp` en su JSON; con `default_factory` el campo se rellena con
la hora de *lectura* al validar (no la real). Aceptado como caveat: la BD solo tiene
datos de prueba (C3 se mergeó hoy) y el dato se estabiliza en el siguiente `save`. Se
documenta en el docstring del campo.

**Frontend — ya está casi listo para consumirlo:**

- Los componentes ya renderizan `message.timestamp` con guard para null:
  [MessageBubble.vue:23](frontend/src/features/chat/components/MessageBubble.vue#L23) y
  las 5 tarjetas (Quote, Recommendation, Compare, Consent, Success) con el mismo patrón
  `v-if="message.timestamp"` + `formatTime` (`toLocaleTimeString('es-CO')` — acepta
  ISO string sin cambios).
- La brecha está en [useChat.js](frontend/src/features/chat/composables/useChat.js):
  `mapSessionMessages` (hidratación tras reload, línea 24-31) pasa `timestamp: null` →
  el historial restaurado pierde las horas; `syncMessagesFromSession` (línea 49-67)
  reusa los timestamps locales pintados o `now` — ignora los del servidor.

**Tests:** ningún test aserta igualdad de dict completo sobre `Message` (revisado
[test_schemas.py](backend/tests/test_schemas.py), que usa asserts por atributo) — un
campo opcional nuevo es aditivo. En ejecución se re-verifica con grep por
`model_dump() ==` antes de tocar el schema.

## Decisiones pendientes (bloqueantes)

(ninguna — resueltas en el análisis:)

- **Formato**: string ISO-8601 UTC (`datetime.now(timezone.utc).isoformat()`), igual
  que `consent_timestamp` — consistente y JSON-directo, sin tipos nuevos en el contrato.
- **`default_factory` en el schema** en vez de setear el campo en los 13 sitios de
  creación: cambio mínimo, imposible olvidar un sitio. Caveat de datos viejos aceptado
  (solo datos de prueba, documentado).
- **El campo es `Optional[str]`** para que payloads externos sin timestamp sigan
  validando (p. ej. el `message` opcional de `ConversationCreate`).

## Principios

- Verde por fase: `.venv\Scripts\python.exe -m pytest -q` (backend) / `npm run build`
  (frontend); ambos servidores levantan.
- **Backend primero**: el frontend consume un campo que ya existe.
- Contrato HTTP explícito: el cambio es **aditivo** (campo nuevo opcional en el shape
  de `messages[]`); nada existente cambia de nombre, tipo ni status code.
- Alcance mínimo: cero dependencias nuevas, cero cambios en repos/modelos SQLModel,
  cero cambios de env vars.

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | ambos | Ninguno | 5m | _(sin commit)_ |
| 1 | Timestamp por mensaje en el schema + tests | backend | Aditivo | 25m | `feat(back): add per-message timestamp to history` |
| 2 | Chat web pinta la hora real del servidor | frontend | Aditivo | 20m | `feat(front): render server message timestamps` |

Total estimado: ~50m.

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: ambos
**Objetivo**: confirmar punto de partida verde tras el merge de C3.
**Archivos afectados**: ninguno (solo lectura).
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Backend: desde `backend/`, `.venv\Scripts\python.exe -m pytest -q` (esperado:
   334 passed, 9 skipped).
2. Frontend: desde `frontend/`, `npm run build` (esperado: OK).
3. Verificar con grep que ningún test aserta dicts completos de `Message`
   (`model_dump() ==` sobre mensajes) que el campo nuevo pueda romper.
**Pruebas / verificación**: los comandos de arriba en verde.
**Riesgos**: ninguno.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit — fase de solo lectura)_

---

## Fase 1 — Timestamp por mensaje en el schema + tests

**Proyecto**: backend
**Objetivo**: todo mensaje nuevo queda sellado con su hora de creación y eso persiste
y se expone en la API; los datos viejos siguen validando.
**Archivos afectados**:
[conversation.py (schemas)](backend/app/schemas/conversation.py#L16-L20) ·
[test_schemas.py](backend/tests/test_schemas.py) ·
[test_conversation_repository.py](backend/tests/test_conversation_repository.py) ·
[test_conversation_service.py](backend/tests/test_conversation_service.py)
**Impacto en contrato API (front↔back)**: **Sí (aditivo)** — cada elemento de
`messages[]` en `ConversationResponse` gana `timestamp: string | null` (ISO-8601 UTC).
Nada existente cambia. El frontend lo consume en la **Fase 2**; mientras tanto lo
ignora sin romperse (los componentes ya tienen guard `v-if`).
**Acciones**:
1. En `Message`, agregar
   `timestamp: Optional[str] = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())`
   con docstring corto: sellado al crear; en datos persistidos antes del campo se
   rellena al leer (caveat documentado, solo afecta datos de prueba pre-cambio).
2. Tests nuevos:
   - `test_schemas.py`: un `Message` nuevo trae timestamp ISO parseable y UTC; un
     payload sin `timestamp` valida con el factory (compat datos viejos).
   - `test_conversation_service.py`: los mensajes que agrega el flujo (p. ej.
     `update_profile`) traen timestamp no nulo.
   - `test_conversation_repository.py`: roundtrip por el repo conserva el timestamp
     EXACTO (guardar → recrear repo → mismo valor, no re-generado).
3. Correr la suite completa (los 13 sitios de creación no se tocan — el factory cubre
   todo).
**Pruebas / verificación**: pytest en verde; manual rápido: `POST /api/v1/conversations`
+ `GET /api/v1/conversations/{id}` → cada mensaje trae `timestamp`; reiniciar uvicorn →
los timestamps NO cambian (persistidos). Negativo: crear conversación con `message`
sin timestamp en el body → 201, nunca 500.
**Riesgos**: tests que comparen `model_dump()` completo de mensajes (mitigado en
pre-flight con grep); mensajes "user" del canal WhatsApp pasan por los mismos services
→ cubiertos por el factory.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `feat(back): add per-message timestamp to history`

---

## Fase 2 — Chat web pinta la hora real del servidor

**Proyecto**: frontend
**Objetivo**: al rehidratar tras un reload (y en cada sync), el chat muestra la hora
real de cada mensaje según el servidor, en vez de null o la hora local de pintado.
**Archivos afectados**:
[useChat.js](frontend/src/features/chat/composables/useChat.js)
**Impacto en contrato API (front↔back)**: No (consume el campo aditivo de la Fase 1;
tolera `timestamp` null — datos viejos — con el guard ya existente en los componentes).
**Acciones**:
1. `mapSessionMessages` (líneas 24-31): pasar
   `message.timestamp ? new Date(message.timestamp) : null` en vez de `null` fijo.
2. `syncMessagesFromSession` (líneas 49-67): preferir el timestamp del servidor cuando
   venga (`new Date(message.timestamp)`); mantener el fallback actual
   (`previousTimestamps` / `now`) para mensajes sin campo.
3. Sin cambios en componentes (ya renderizan con guard) ni en `api.js` (mismo shape).
**Pruebas / verificación**: `npm run build` OK; manual: conversar, recargar la página →
el historial restaurado muestra horas (antes desaparecían); con API caída el chat
sigue mostrando la burbuja de error, no pantalla rota (camino no tocado). Datos
viejos sin timestamp → la hora simplemente no se muestra (guard `v-if`).
**Riesgos**: `formatTime` usa `toLocaleTimeString` sobre `Date` — un ISO inválido
daría "Invalid Date"; se construye `Date` solo si el campo viene (string ISO del
backend).

🛑 **CHECKPOINT FINAL** — Con esto el criterio 2 de C3 queda completo (rol, contenido
y timestamp por mensaje, consultable por conversación y visible en el chat). Marcar
la brecha como resuelta en el veredicto del brain.
**Commit sugerido**: `feat(front): render server message timestamps`
