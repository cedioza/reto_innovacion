"""Tests para el adaptador de canales y el channel gateway — TDD RED phase.

Cubre la Fase 1 del plan F1 (`.claude/analysis/plans/
20260726-f1-webhooks-conectados-orquestador.plan.md`): `app/services/
channels/base.py` (helpers puros de formato/segmentación de texto) y
`app/services/channel_gateway.py` (el punto único por el que TODOS los
canales — WhatsApp, Telegram o cualquier canal futuro — entran al
orquestador conversacional `app.services.orchestrator`, o caen al
`ChannelHandler` legado mientras no haya `gemini_api_key`).

Ni `app.services.channels` ni `app.services.channel_gateway` existen
todavía: cada test de este archivo debe fallar con
`ModuleNotFoundError`/`ImportError` hasta que la Fase 2 los implemente. El
LLM siempre se guiona vía `monkeypatch` de `orchestrator.generate_reply`
(sin red), igual que en `test_orchestrator.py`.
"""

from __future__ import annotations

from app.core.config import settings
from app.repositories import db as db_module
from app.repositories.channel_sessions import ChannelSessionRepository
from app.services.channel_handler import ChannelHandler
from app.services.conversation import conversation_service
from app.services.integrations.gemini_client import GeminiReply

import app.services.channel_gateway as channel_gateway
import app.services.orchestrator as orchestrator
from app.services.channels.base import (
    InboundMessage,
    markdown_bold_to_whatsapp,
    split_text,
)


# -- helpers -----------------------------------------------------------------


def _scripted_llm(replies: list[GeminiReply]):
    """Fábrica de un `generate_reply` guionado (mismo patrón que test_orchestrator.py).

    Devuelve una función con la firma de
    `generate_reply(contents, *, tools=None, system_instruction=None)` que
    responde con `replies` en orden y registra cada llamada en `.calls`. Si
    el guion se agota, falla con `AssertionError` (sirve también como espía:
    pasarle una lista vacía y comprobar que `.calls` sigue vacía).
    """

    calls: list[dict] = []

    def _generate_reply(contents, *, tools=None, system_instruction=None):
        calls.append(
            {
                "contents": contents,
                "tools": tools,
                "system_instruction": system_instruction,
            }
        )
        assert len(calls) <= len(replies), (
            "LLM script exhausted: more calls than scripted replies"
        )
        return replies[len(calls) - 1]

    _generate_reply.calls = calls
    return _generate_reply


FAVORABLE_ARGS = {
    "property_type": "house",
    "zone": "urban",
    "stratum": 3,
    "age_range": "26-40",
}


# -- TestHelpers ---------------------------------------------------------


class TestHelpers:
    def test_split_text_no_corta_palabras_y_respeta_el_limite(self) -> None:
        words = [f"palabra{i}" for i in range(1500)]
        paragraphs = []
        for start in range(0, len(words), 60):
            paragraphs.append(" ".join(words[start : start + 60]))
        text = "\n\n".join(paragraphs)
        assert len(text) > 9000

        chunks = split_text(text, 4096)

        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 4096

        # Ningún trozo corta una palabra a la mitad: uniendo todos los
        # trozos con un espacio y volviendo a tokenizar por espacios en
        # blanco se debe reconstruir exactamente la lista original de
        # palabras, en el mismo orden.
        rejoined_tokens = " ".join(chunks).split()
        assert rejoined_tokens == words

    def test_split_text_texto_corto_devuelve_un_solo_trozo(self) -> None:
        assert split_text("hola mundo", 4096) == ["hola mundo"]

    def test_split_text_texto_vacio_devuelve_lista_vacia(self) -> None:
        assert split_text("", 4096) == []

    def test_markdown_bold_to_whatsapp_convierte_asteriscos_dobles(self) -> None:
        assert (
            markdown_bold_to_whatsapp("**hola** y *chao*") == "*hola* y *chao*"
        )

    def test_inbound_message_expone_channel_user_ref_text(self) -> None:
        message = InboundMessage(
            channel="whatsapp", user_ref="573001112233", text="hola"
        )
        assert message.channel == "whatsapp"
        assert message.user_ref == "573001112233"
        assert message.text == "hola"


# -- TestHandleConKey ------------------------------------------------------


class TestHandleConKey:
    def test_primer_mensaje_crea_sesion_y_responde(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "gemini_api_key", "dummy-key")
        llm = _scripted_llm(
            [GeminiReply(kind="text", text="¡Hola! ¿En qué te ayudo?")]
        )
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        result = channel_gateway.handle(
            "whatsapp", "573000000001", "hola"
        )

        assert result == "¡Hola! ¿En qué te ayudo?"

        repo = ChannelSessionRepository()
        session_id = repo.find("whatsapp", "573000000001")
        assert session_id is not None

        session = conversation_service.get(session_id)
        assert session is not None
        contents = [message.content for message in session.messages]
        assert "hola" in contents
        assert "¡Hola! ¿En qué te ayudo?" in contents

    def test_segundo_mensaje_reusa_sesion(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "gemini_api_key", "dummy-key")
        llm = _scripted_llm(
            [
                GeminiReply(kind="text", text="primera respuesta"),
                GeminiReply(kind="text", text="segunda respuesta"),
            ]
        )
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        channel_gateway.handle("whatsapp", "573000000002", "hola")
        repo = ChannelSessionRepository()
        session_id_first = repo.find("whatsapp", "573000000002")

        result_second = channel_gateway.handle(
            "whatsapp", "573000000002", "otro mensaje"
        )
        session_id_second = repo.find("whatsapp", "573000000002")

        assert session_id_first is not None
        assert session_id_first == session_id_second
        assert result_second == "segunda respuesta"

        session = conversation_service.get(session_id_first)
        assert session is not None
        assert len(session.messages) >= 4

    def test_retoma_tras_redeploy(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "gemini_api_key", "dummy-key")
        llm = _scripted_llm(
            [
                GeminiReply(kind="text", text="hola de nuevo"),
                GeminiReply(kind="text", text="segundo turno post-redeploy"),
            ]
        )
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        channel_gateway.handle("telegram", "user-redeploy-001", "hola")

        # Simula un proceso nuevo: instancias frescas de repo/servicio sobre
        # el MISMO engine (criterio 2 de F1: la sesión sobrevive un
        # redeploy porque vive en la base de datos, no en memoria Python).
        fresh_repo = ChannelSessionRepository(engine=db_module._engine)
        session_id_before = fresh_repo.find("telegram", "user-redeploy-001")
        assert session_id_before is not None
        assert conversation_service.get(session_id_before) is not None

        result_second = channel_gateway.handle(
            "telegram", "user-redeploy-001", "sigo aca"
        )

        session_id_after = fresh_repo.find("telegram", "user-redeploy-001")
        assert session_id_after == session_id_before
        assert result_second == "segundo turno post-redeploy"

    def test_canal_ficticio_funciona_identico(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "gemini_api_key", "dummy-key")
        llm = _scripted_llm(
            [GeminiReply(kind="text", text="hola desde canal inventado")]
        )
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        result = channel_gateway.handle(
            "canal-inventado", "user-ficticio-001", "hola"
        )

        assert result == "hola desde canal inventado"
        repo = ChannelSessionRepository()
        assert repo.find("canal-inventado", "user-ficticio-001") is not None

    def test_sesion_huerfana_se_recrea(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "gemini_api_key", "dummy-key")
        repo = ChannelSessionRepository()
        repo.save("whatsapp", "user-huerfano-001", "session-inexistente")

        llm = _scripted_llm([GeminiReply(kind="text", text="te ayudo de nuevo")])
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        result = channel_gateway.handle(
            "whatsapp", "user-huerfano-001", "hola"
        )

        assert result == "te ayudo de nuevo"
        new_session_id = repo.find("whatsapp", "user-huerfano-001")
        assert new_session_id is not None
        assert new_session_id != "session-inexistente"
        assert conversation_service.get(new_session_id) is not None

    def test_respuesta_incluye_tarjetas_del_turno(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "gemini_api_key", "dummy-key")
        llm = _scripted_llm(
            [
                GeminiReply(
                    kind="tool_call",
                    tool_name="perfilar_cliente",
                    tool_args=dict(FAVORABLE_ARGS),
                ),
                GeminiReply(
                    kind="tool_call", tool_name="recomendar_seguro", tool_args={}
                ),
                GeminiReply(kind="text", text="Te recomiendo este seguro"),
            ]
        )
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        result = channel_gateway.handle(
            "whatsapp", "user-tarjetas-001", "quiero un seguro"
        )

        assert "Te recomiendo este seguro" in result
        assert "📋" in result
        assert "Recomendación" in result


# -- TestHandleSinKey --------------------------------------------------------


class TestHandleSinKey:
    def test_handle_sin_key_delega_en_legacy_handler(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "gemini_api_key", "")

        generate_reply_spy = _scripted_llm([])
        monkeypatch.setattr(orchestrator, "generate_reply", generate_reply_spy)

        legacy_calls: list[tuple[str, str, str]] = []

        def _fake_handle_incoming(self, channel, user_id, text):
            legacy_calls.append((channel, user_id, text))
            return "respuesta legacy"

        monkeypatch.setattr(ChannelHandler, "handle_incoming", _fake_handle_incoming)

        result = channel_gateway.handle(
            "whatsapp", "573000099999", "hola"
        )

        assert result == "respuesta legacy"
        assert legacy_calls == [("whatsapp", "573000099999", "hola")]
        assert len(generate_reply_spy.calls) == 0
