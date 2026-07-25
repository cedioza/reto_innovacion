"""Cliente de bajo nivel para la API de Gemini (`generateContent`).

Este módulo solo sabe hablar HTTP/JSON con Gemini: construye el payload,
hace la llamada (con un reintento ante errores de red o 5xx) y traduce la
respuesta a un `GeminiReply`. No ejecuta herramientas de negocio ni conoce
las capas de `services`/`repositories` de la aplicación: eso vive en el
service que use este cliente (fases siguientes del plan).
"""

import base64
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


def audio_part(data: bytes, mime_type: str = "audio/ogg") -> dict:
    """Construye una `part` de audio inline (base64) para el formato de Gemini."""
    return {
        "inline_data": {
            "mime_type": mime_type,
            "data": base64.b64encode(data).decode(),
        }
    }


def function_call_part(name: str, args: dict) -> dict:
    """Construye una `part` de tipo `functionCall` (petición de Gemini a usar una herramienta)."""
    return {"functionCall": {"name": name, "args": args}}


def function_response_part(name: str, response: dict) -> dict:
    """Construye una `part` de tipo `functionResponse` (resultado de una herramienta para Gemini)."""
    return {"functionResponse": {"name": name, "response": response}}


def user_message(*parts: dict) -> dict:
    """Construye un mensaje de rol `user` con las `parts` dadas."""
    return {"role": "user", "parts": list(parts)}


def model_message(*parts: dict) -> dict:
    """Construye un mensaje de rol `model` con las `parts` dadas."""
    return {"role": "model", "parts": list(parts)}


def _parts_from_response(response_json: dict) -> list:
    """Extrae `candidates[0].content.parts`, defensivo en cada nivel."""
    candidates = response_json.get("candidates") or []
    if not candidates:
        return []
    first_candidate = candidates[0] or {}
    content = first_candidate.get("content") or {}
    return content.get("parts") or []


def _extract_text(parts: list) -> str:
    """Concatena los textos de una lista de `parts`, defensivo."""
    texts = [part.get("text", "") for part in parts if isinstance(part, dict)]
    return "".join(texts)


def _extract_function_call(parts: list) -> dict | None:
    """Devuelve la primera `functionCall` encontrada en `parts`, si hay alguna."""
    for part in parts:
        if not isinstance(part, dict):
            continue
        function_call = part.get("functionCall")
        if function_call:
            return function_call
    return None


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
    if tools is not None:
        payload["tools"] = [{"functionDeclarations": tools}]

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
            parts = _parts_from_response(response.json())
            function_call = _extract_function_call(parts)
            if function_call is not None:
                return GeminiReply(
                    kind="tool_call",
                    tool_name=function_call.get("name", ""),
                    tool_args=function_call.get("args") or {},
                )
            return GeminiReply(kind="text", text=_extract_text(parts))

        if response.status_code >= 500 and attempt < MAX_ATTEMPTS - 1:
            continue

        return GeminiReply(kind="error", text=FALLBACK_MESSAGE)

    return GeminiReply(kind="error", text=FALLBACK_MESSAGE)
