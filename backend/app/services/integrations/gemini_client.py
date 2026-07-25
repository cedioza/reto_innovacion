"""Cliente de bajo nivel para la API de Gemini (`generateContent`).

Este módulo solo sabe hablar HTTP/JSON con Gemini: construye el payload,
hace la llamada (con reintentos ante errores de red, 5xx o 429 por rate
limit) y traduce la respuesta a un `GeminiReply`. No ejecuta herramientas
de negocio ni conoce
las capas de `services`/`repositories` de la aplicación: eso vive en el
service que use este cliente (fases siguientes del plan).
"""

import base64
import time
from dataclasses import dataclass, field
from typing import Literal

import httpx

GEMINI_MODEL = "gemini-flash-latest"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
TIMEOUT = 30
MAX_ATTEMPTS = 2
FALLBACK_MESSAGE = "Lo siento, tuve un problema técnico. ¿Intentamos de nuevo?"

# Reintentos ante 429 (rate limit del free tier de Gemini): son frecuentes en
# conversaciones con varias llamadas seguidas (tool calling) y, a diferencia
# de otros 4xx, sí conviene reintentar. Van en un presupuesto aparte de
# `MAX_ATTEMPTS` (que rige red/5xx) para darles más margen.
MAX_RATE_LIMIT_RETRIES = 2
RATE_LIMIT_BACKOFF_SECONDS = (2.0, 4.0)
# Tope al `retryDelay` que sugiere el body del 429: Google a veces pide ~30s,
# demasiado para no bloquear la respuesta al usuario; preferimos reintentar
# antes y, si sigue en 429, devolver el fallback.
MAX_RATE_LIMIT_DELAY_SECONDS = 5.0


def _sleep(seconds: float) -> None:
    """Espera bloqueante, aislada en su propia función para poder parchearla en tests."""
    time.sleep(seconds)


def _rate_limit_delay_seconds(response: httpx.Response, attempt_index: int) -> float:
    """Segundos a esperar antes de reintentar un 429.

    Usa el `retryDelay` que Gemini sugiere en `error.details` del body (p. ej.
    `"retryDelay": "30s"`), acotado a `MAX_RATE_LIMIT_DELAY_SECONDS`. Si el
    body no trae esa información, cae al backoff fijo `RATE_LIMIT_BACKOFF_SECONDS`.
    """
    try:
        body = response.json()
    except ValueError:
        body = {}
    details = ((body.get("error") or {}).get("details")) or []
    for detail in details:
        if not isinstance(detail, dict):
            continue
        retry_delay = detail.get("retryDelay")
        if isinstance(retry_delay, str) and retry_delay.endswith("s"):
            try:
                return min(float(retry_delay[:-1]), MAX_RATE_LIMIT_DELAY_SECONDS)
            except ValueError:
                continue
    index = min(attempt_index, len(RATE_LIMIT_BACKOFF_SECONDS) - 1)
    return RATE_LIMIT_BACKOFF_SECONDS[index]


@dataclass
class GeminiReply:
    """Resultado normalizado de una llamada a `generate_reply`."""

    kind: Literal["text", "tool_call", "error"]
    text: str = ""
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)
    thought_signature: str = ""


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


def function_call_part(name: str, args: dict, thought_signature: str = "") -> dict:
    """Construye una `part` de tipo `functionCall` (petición de Gemini a usar una herramienta).

    Si `thought_signature` no está vacío, se incluye como `thoughtSignature`:
    Gemini 3 exige reenviar la firma de pensamiento original al reconstruir el
    historial, o rechaza la siguiente llamada con 400 INVALID_ARGUMENT.
    """
    part: dict = {"functionCall": {"name": name, "args": args}}
    if thought_signature:
        part["thoughtSignature"] = thought_signature
    return part


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


def _extract_function_call_part(parts: list) -> dict | None:
    """Devuelve la primera `part` con `functionCall` encontrada en `parts`, si hay alguna."""
    for part in parts:
        if not isinstance(part, dict):
            continue
        if part.get("functionCall"):
            return part
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

    network_attempt = 0
    rate_limit_attempt = 0
    while True:
        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                response = client.post(GEMINI_URL, json=payload, headers=headers)
        except httpx.HTTPError:
            if network_attempt < MAX_ATTEMPTS - 1:
                network_attempt += 1
                continue
            return GeminiReply(kind="error", text=FALLBACK_MESSAGE)

        if response.is_success:
            parts = _parts_from_response(response.json())
            function_call_part_found = _extract_function_call_part(parts)
            if function_call_part_found is not None:
                function_call = function_call_part_found["functionCall"]
                return GeminiReply(
                    kind="tool_call",
                    tool_name=function_call.get("name", ""),
                    tool_args=function_call.get("args") or {},
                    thought_signature=function_call_part_found.get(
                        "thoughtSignature", ""
                    ),
                )
            return GeminiReply(kind="text", text=_extract_text(parts))

        if response.status_code == 429 and rate_limit_attempt < MAX_RATE_LIMIT_RETRIES:
            _sleep(_rate_limit_delay_seconds(response, rate_limit_attempt))
            rate_limit_attempt += 1
            continue

        if response.status_code >= 500 and network_attempt < MAX_ATTEMPTS - 1:
            network_attempt += 1
            continue

        return GeminiReply(kind="error", text=FALLBACK_MESSAGE)
