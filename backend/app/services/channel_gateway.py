"""Punto único de entrada de todos los canales al orquestador conversacional.

`handle` es la función que llaman los webhooks de canal (WhatsApp, Telegram,
o cualquier canal futuro): recibe ya el trío traducido `(channel, user_ref,
text)` — ver `app.services.channels.base.InboundMessage` — y devuelve el
texto de respuesta como una sola cadena, sin ningún formato específico de
proveedor (eso es responsabilidad del adaptador de canal, no de este
módulo). El canal jamás se inspecciona por nombre aquí: `channel` solo se
usa como parte de la clave de sesión `(channel, user_ref)` en
`ChannelSessionRepository`, nunca en un `if channel == "whatsapp"` — así un
canal nuevo funciona igual sin tocar este archivo.

Todo lo que no es traducción de formato de un proveedor concreto vive
detrás de `handle`:

- Si no hay `gemini_api_key` configurada (H0-H4, antes de tener LLM), se
  delega en el `ChannelHandler` legado (máquina de estados por regex sobre
  el texto) — ese es el "fallback regex" documentado para desaparecer
  cuando H5 quede completo y el orquestador conversacional (LLM +
  `agent_tools`) sea la única vía.
- Con `gemini_api_key` configurada, se resuelve (o crea) la sesión de
  conversación asociada a `(channel, user_ref)` vía
  `ChannelSessionRepository` — persistida en base de datos, no en memoria
  Python, para sobrevivir un redeploy — y se ejecuta un turno completo con
  `app.services.orchestrator.respond`. La respuesta es la concatenación de
  los mensajes de rol `"assistant"` que ese turno agregó a la sesión (texto
  del LLM más las tarjetas de recomendación/cotización/comparación/
  aplicación que el turno haya generado), unidos con doble salto de línea.
"""

from __future__ import annotations

from sqlalchemy import Engine

from app.core.config import settings
from app.repositories.channel_sessions import ChannelSessionRepository
from app.schemas.conversation import ConversationCreate
from app.services import orchestrator
from app.services.channel_handler import ChannelHandler
from app.services.conversation import conversation_service


def handle(
    channel: str, user_ref: str, text: str, engine: Engine | None = None
) -> str:
    """Procesa un mensaje entrante de cualquier canal y devuelve el texto de respuesta.

    `engine` permite inyectar un engine de base de datos explícito (usado en
    tests para simular un redeploy sobre el mismo engine); si se omite, cada
    repositorio resuelve el engine global por defecto.
    """
    if not settings.gemini_api_key:
        return ChannelHandler(engine=engine).handle_incoming(channel, user_ref, text)

    repo = ChannelSessionRepository(engine=engine)
    session_id = repo.find(channel, user_ref)
    session = conversation_service.get(session_id) if session_id is not None else None

    if session is None:
        session = conversation_service.create(ConversationCreate())
        session_id = session.session_id
        repo.save(channel, user_ref, session_id)

    before = len(session.messages)
    session = orchestrator.respond(session_id, text)
    new_messages = session.messages[before:]

    return "\n\n".join(
        message.content for message in new_messages if message.role == "assistant"
    )
