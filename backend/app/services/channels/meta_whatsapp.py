"""Adaptador de canal para Meta WhatsApp Cloud API (Fase 2, plan F1).

Implementa el contrato de `app.services.channels.base` para el canal
WhatsApp vía Meta Cloud API:

- **Entrada** (`parse_incoming`): traduce el payload crudo del webhook de
  Meta (`entry[0].changes[0].value.messages[0]`) a un `InboundMessage`. Solo
  se reconocen mensajes de texto (`type == "text"`) y respuestas de botón
  interactivo (`type == "interactive"` con `interactive.button_reply`, cuyo
  `title` se usa como texto) — cualquier otro caso, payload malformado o
  ausencia de mensajes devuelve `None` sin lanzar excepciones, tal como hacía
  el parsing inline que reemplaza en `app.api.routes.webhooks`.
- **Salida** (`deliver`): traduce el texto de respuesta del orquestador al
  formato de WhatsApp (negrita Markdown → un solo asterisco vía
  `markdown_bold_to_whatsapp`) y lo trocea al límite de 4096 caracteres de la
  Cloud API (`split_text`), enviando cada fragmento en orden vía
  `send_whatsapp_message`. Corta en el primer envío fallido.
"""

from __future__ import annotations

from app.services.channels.base import (
    InboundMessage,
    markdown_bold_to_whatsapp,
    split_text,
)
from app.services.whatsapp_provider import send_whatsapp_message

_WHATSAPP_TEXT_LIMIT = 4096


class MetaWhatsAppAdapter:
    """Adaptador de canal para WhatsApp vía Meta Cloud API."""

    channel = "whatsapp"

    def parse_incoming(self, payload: dict) -> InboundMessage | None:
        """Traduce el payload del webhook de Meta a un `InboundMessage`.

        Devuelve `None` si el payload no trae un mensaje reconocible (sin
        `entry`/`changes`/`messages`, o un tipo de mensaje sin texto
        asociado) — nunca lanza excepciones.
        """
        entry = payload.get("entry", [])
        if not entry:
            return None

        changes = entry[0].get("changes", [])
        if not changes:
            return None

        value = changes[0].get("value", {})
        messages = value.get("messages", [])

        if not messages:
            return None

        msg = messages[0]
        phone = msg.get("from", "")
        msg_type = msg.get("type", "")
        text = ""

        if msg_type == "text":
            text = msg.get("text", {}).get("body", "")
        elif msg_type == "interactive":
            interactive = msg.get("interactive", {})
            button_reply = interactive.get("button_reply", {})
            text = button_reply.get("title", "")

        if not text:
            return None

        return InboundMessage(self.channel, phone, text)

    def deliver(self, user_ref: str, text: str) -> bool:
        """Envía `text` a `user_ref` en formato WhatsApp, troceado por límite.

        Traduce negrita Markdown al formato de WhatsApp y divide el texto en
        fragmentos de a lo sumo `_WHATSAPP_TEXT_LIMIT` caracteres, enviándolos
        en orden. Corta en el primer envío fallido (devuelve `False`); texto
        vacío no envía nada y devuelve `True`.
        """
        formatted = markdown_bold_to_whatsapp(text)
        chunks = split_text(formatted, _WHATSAPP_TEXT_LIMIT)

        for chunk in chunks:
            if not send_whatsapp_message(user_ref, chunk):
                return False

        return True
