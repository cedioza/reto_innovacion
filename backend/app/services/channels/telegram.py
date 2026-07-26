"""Adaptador de canal para Telegram Bot API (Fase 1, plan F5).

Implementa el contrato de `app.services.channels.base` para el canal
Telegram, siguiendo el mismo patrón que
`app.services.channels.meta_whatsapp` (plan C de canal — WhatsApp fue el
primero en enchufarse al contrato de adaptador, Telegram es el segundo):

- **Entrada** (`parse_incoming`): traduce el `Update` crudo del webhook de
  Telegram (`message.chat.id`, con fallback a `message.from.id` cuando el
  chat no viene en el payload) a un `InboundMessage`. Requiere también
  `message.text`; cualquier ausencia o payload basura devuelve `None` sin
  lanzar excepciones. El `user_ref` resultante siempre es `str(chat_id)`,
  aunque Telegram mande el id como entero.
- **Salida** (`deliver`): al igual que el Markdown legacy de WhatsApp,
  el formato de negrita que reconoce Telegram (modo `Markdown`, no
  `MarkdownV2`) comparte con WhatsApp el único asterisco (`*texto*`) en vez
  del `**texto**` estándar, así que reutiliza el mismo
  `markdown_bold_to_whatsapp` y `split_text` de `app.services.channels.base`.
  Si el envío de un fragmento falla, se reintenta ESE MISMO fragmento en
  texto plano (`parse_mode=None`) por si la falla fue un Markdown roto
  (asteriscos sin cerrar, por ejemplo); si el reintento también falla,
  `deliver` corta sin enviar el resto de los fragmentos.
"""

from __future__ import annotations

from app.services.channels.base import (
    InboundMessage,
    markdown_bold_to_whatsapp,
    split_text,
)
from app.services.telegram_client import send_telegram_message

_TELEGRAM_TEXT_LIMIT = 4096


class TelegramAdapter:
    """Adaptador de canal para Telegram vía Bot API."""

    channel = "telegram"

    def parse_incoming(self, payload: dict) -> InboundMessage | None:
        """Traduce el `Update` del webhook de Telegram a un `InboundMessage`.

        Lee `message.chat.id` con fallback a `message.from.id`; requiere
        también `message.text`. Devuelve `None` si falta cualquiera de los
        dos, o si el payload es basura — nunca lanza excepciones.
        """
        message = payload.get("message", {})
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        if chat_id is None:
            chat_id = message.get("from", {}).get("id")

        text = message.get("text", "")

        if chat_id is None or not text:
            return None

        return InboundMessage(self.channel, str(chat_id), text)

    def deliver(self, user_ref: str, text: str) -> bool:
        """Envía `text` a `user_ref` en formato Telegram, troceado por límite.

        Traduce negrita Markdown al único asterisco que Telegram reconoce y
        divide el texto en fragmentos de a lo sumo `_TELEGRAM_TEXT_LIMIT`
        caracteres, enviándolos en orden. Si un fragmento falla, reintenta
        ese mismo fragmento con `parse_mode=None` (texto plano); si el
        reintento también falla, corta sin enviar el resto (devuelve
        `False`). Texto vacío no envía nada y devuelve `True`.
        """
        formatted = markdown_bold_to_whatsapp(text)
        chunks = split_text(formatted, _TELEGRAM_TEXT_LIMIT)

        for chunk in chunks:
            if send_telegram_message(user_ref, chunk):
                continue
            if not send_telegram_message(user_ref, chunk, parse_mode=None):
                return False

        return True
