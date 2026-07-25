"""Tests LIVE contra la API real de Gemini (`generate_reply`).

GATED: la suite normal (`pytest`) NO ejecuta estos tests. Requieren
`RUN_LIVE_GEMINI_TESTS=1` y una `GEMINI_API_KEY` real en el entorno/`.env`,
porque hacen llamadas HTTP reales que gastan créditos. Se corren a propósito
y de forma explícita:

    RUN_LIVE_GEMINI_TESTS=1 pytest tests/test_gemini_client_live.py -q

Son tolerantes a la variación del texto que devuelve el LLM (no assertan
contenido exacto), pero NO deben pasar si el cliente cae en el fallback de
error: eso significa que algo de la integración real está roto.
"""

import io
import math
import os
import struct
import wave

import pytest

from app.services.integrations.gemini_client import (
    audio_part,
    generate_reply,
    text_part,
    user_message,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_GEMINI_TESTS") != "1",
    reason="live: requiere RUN_LIVE_GEMINI_TESTS=1 y GEMINI_API_KEY real (gasta créditos)",
)

_COTIZAR_DECLARATION = {
    "name": "cotizar",
    "description": "Cotiza un producto de seguros.",
    "parameters": {
        "type": "object",
        "properties": {"producto": {"type": "string"}},
    },
}


def _make_tone_wav_bytes(
    duration_seconds: float = 0.5,
    frequency_hz: float = 440.0,
    sample_rate: int = 16000,
) -> bytes:
    """Genera un WAV mono 16-bit con un tono senoidal corto, en memoria."""
    n_samples = int(duration_seconds * sample_rate)
    amplitude = 32767 * 0.5

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        frames = bytearray()
        for i in range(n_samples):
            sample = int(amplitude * math.sin(2 * math.pi * frequency_hz * i / sample_rate))
            frames += struct.pack("<h", sample)
        wav_file.writeframes(bytes(frames))

    return buffer.getvalue()


def test_live_text_with_tool_declared():
    reply = generate_reply(
        [user_message(text_part("hola"))],
        tools=[_COTIZAR_DECLARATION],
        system_instruction="Eres un asesor de seguros. Saluda brevemente.",
    )

    assert reply.kind == "text"
    assert reply.text.strip() != ""


def test_live_forced_tool_call():
    reply = generate_reply(
        [
            user_message(
                text_part(
                    "Cotiza un seguro de hogar para estrato 3 en Bogotá. "
                    "Usa la herramienta cotizar."
                )
            )
        ],
        tools=[_COTIZAR_DECLARATION],
        system_instruction=(
            "Eres un asesor de seguros. Usa las herramientas disponibles cuando apliquen."
        ),
    )

    assert reply.kind == "tool_call"
    assert reply.tool_name == "cotizar"
    assert isinstance(reply.tool_args, dict)


def test_live_audio_interpretation():
    wav_bytes = _make_tone_wav_bytes()

    reply = generate_reply(
        [
            user_message(
                audio_part(wav_bytes, mime_type="audio/wav"),
                text_part("Describe brevemente qué se oye en el audio."),
            )
        ]
    )

    assert reply.kind == "text"
    assert reply.text.strip() != ""
