"""Contrato único de adaptador de canal.

Un "canal" (WhatsApp, Telegram, o cualquier canal futuro) es, de cara al
resto del sistema, una simple traducción de formato en dos direcciones:

- **Entrada**: el payload crudo que manda el proveedor (JSON de WhatsApp
  Cloud API, `Update` de Telegram, ...) se traduce a un `InboundMessage`:
  el trío mínimo `(channel, user_ref, text)` que necesita
  `app.services.channel_gateway.handle` para resolver la sesión de
  conversación y ejecutar un turno con el orquestador — sin que ese código
  necesite saber nada del proveedor concreto.
- **Salida**: el texto que devuelve el orquestador (una sola cadena, sin
  límite de longitud ni formato particular) se traduce a lo que el canal
  necesita para entregarlo: WhatsApp exige fragmentos por debajo de un
  límite de caracteres (`split_text`) y usa un solo asterisco para negritas
  en vez de Markdown estándar (`markdown_bold_to_whatsapp`); Telegram, por
  ejemplo, podría no necesitar ninguna de las dos transformaciones.

Este módulo reúne esos dos extremos del contrato como funciones puras, sin
I/O ni conocimiento del proveedor HTTP concreto: es la "pieza de lego" que
permite que conectar un canal nuevo (F4/F5) sea una tarea de una hora — un
adaptador delgado que llama a estos helpers y al
`app.services.channel_gateway.handle` común a todos los canales, en vez de
reimplementar sesión, orquestación y guardas de precio por canal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Regex del helper de negritas: Markdown estándar (`**texto**`) al único
# asterisco que WhatsApp reconoce como negrita (`*texto*`). No-greedy para
# no fusionar dos negritas separadas en una misma línea.
_MARKDOWN_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


@dataclass
class InboundMessage:
    """Trío mínimo que cualquier adaptador de canal debe producir.

    `channel` identifica el proveedor (p. ej. "whatsapp", "telegram", o
    cualquier nombre inventado — `channel_gateway.handle` nunca lo inspecciona
    por valor, solo lo usa como parte de la clave de sesión), `user_ref` es
    el identificador de usuario propio de ese canal (número de WhatsApp,
    `chat_id` de Telegram, ...) y `text` es el mensaje ya traducido a texto
    plano.
    """

    channel: str
    user_ref: str
    text: str


def split_text(text: str, limit: int) -> list[str]:
    """Divide `text` en fragmentos de a lo sumo `limit` caracteres.

    Nunca corta una palabra a la mitad: intenta dividir primero por
    párrafos (separados por `"\\n\\n"`); si un párrafo por sí solo excede
    `limit`, lo subdivide por renglones (`"\\n"`); si un renglón por sí
    solo sigue excediendo `limit`, lo subdivide por palabras (espacios). En
    el caso extremo de que una sola palabra exceda `limit`, se devuelve tal
    cual (nunca se parte una palabra) — es la única situación en la que un
    fragmento del resultado puede superar `limit`.

    Texto vacío devuelve `[]`; texto que ya cabe en `limit` devuelve una
    lista de un solo elemento con el texto intacto.
    """
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    return _split_by_separator(text, limit, "\n\n", ["\n", " "])


def _split_by_separator(
    text: str, limit: int, sep: str, next_seps: list[str]
) -> list[str]:
    """Empaqueta `text.split(sep)` en fragmentos <= `limit`, uniendo con `sep`.

    Cuando una unidad por sí sola ya excede `limit`, se subdivide
    recursivamente con el siguiente separador de `next_seps` (o se deja tal
    cual, sin cortarla, si ya no quedan separadores más finos que probar).
    """
    units = text.split(sep)
    chunks: list[str] = []
    current = ""

    for unit in units:
        if len(unit) > limit:
            if current:
                chunks.append(current)
                current = ""
            if next_seps:
                chunks.extend(
                    _split_by_separator(unit, limit, next_seps[0], next_seps[1:])
                )
            else:
                chunks.append(unit)
            continue

        candidate = unit if not current else f"{current}{sep}{unit}"
        if len(candidate) <= limit:
            current = candidate
        else:
            chunks.append(current)
            current = unit

    if current:
        chunks.append(current)

    return chunks


def markdown_bold_to_whatsapp(text: str) -> str:
    """Traduce negrita Markdown estándar (`**texto**`) al formato de WhatsApp (`*texto*`)."""
    return _MARKDOWN_BOLD_RE.sub(r"*\1*", text)
