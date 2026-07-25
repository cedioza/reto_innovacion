"""Cliente de bajo nivel para la API de Gemini (`generateContent`).

Este módulo solo sabe hablar HTTP/JSON con Gemini: construye el payload,
hace la llamada (con un reintento ante errores de red o 5xx) y traduce la
respuesta a un `GeminiReply`. No ejecuta herramientas de negocio ni conoce
las capas de `services`/`repositories` de la aplicación: eso vive en el
service que use este cliente (fases siguientes del plan).
"""

from dataclasses import dataclass, field
from typing import Literal

import httpx

GEMINI_MODEL = "gemini-flash-latest"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
TIMEOUT = 30
MAX_ATTEMPTS = 2
FALLBACK_MESSAGE = "Lo siento, tuve un problema técnico. ¿Intentamos de nuevo?"


@dataclass
class GeminiReply:
    """Resultado normalizado de una llamada a `generate_reply`."""

    kind: Literal["text", "tool_call", "error"]
    text: str = ""
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)


def text_part(text: str) -> dict:
    """Construye una `part` de tipo texto para el formato de Gemini."""
    return {"text": text}


def user_message(*parts: dict) -> dict:
    """Construye un mensaje de rol `user` con las `parts` dadas."""
    return {"role": "user", "parts": list(parts)}


def model_message(*parts: dict) -> dict:
    """Construye un mensaje de rol `model` con las `parts` dadas."""
    return {"role": "model", "parts": list(parts)}


def _extract_text(response_json: dict) -> str:
    """Concatena los textos de `candidates[0].content.parts`, defensivo."""
    candidates = response_json.get("candidates") or []
    if not candidates:
        return ""
    first_candidate = candidates[0] or {}
    content = first_candidate.get("content") or {}
    parts = content.get("parts") or []
    texts = [part.get("text", "") for part in parts if isinstance(part, dict)]
    return "".join(texts)


def generate_reply(
    contents: list,
    *,
    tools: list | None = None,
    system_instruction: str | None = None,
) -> GeminiReply:
    """Llama a Gemini con los `contents` dados y devuelve un `GeminiReply`.

    Nunca lanza excepción: cualquier fallo (sin API key, error de red, status
    de error tras agotar reintentos) se traduce en `GeminiReply(kind="error")`
    con `FALLBACK_MESSAGE`, sin filtrar la API key ni la URL en el texto.
    """
    from app.core.config import settings

    if not settings.gemini_api_key:
        return GeminiReply(kind="error", text=FALLBACK_MESSAGE)

    payload: dict = {"contents": contents}
    if system_instruction is not None:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

    headers = {"x-goog-api-key": settings.gemini_api_key}

    for attempt in range(MAX_ATTEMPTS):
        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                response = client.post(GEMINI_URL, json=payload, headers=headers)
        except httpx.HTTPError:
            if attempt < MAX_ATTEMPTS - 1:
                continue
            return GeminiReply(kind="error", text=FALLBACK_MESSAGE)

        if response.is_success:
            text = _extract_text(response.json())
            return GeminiReply(kind="text", text=text)

        if response.status_code >= 500 and attempt < MAX_ATTEMPTS - 1:
            continue

        return GeminiReply(kind="error", text=FALLBACK_MESSAGE)

    return GeminiReply(kind="error", text=FALLBACK_MESSAGE)
