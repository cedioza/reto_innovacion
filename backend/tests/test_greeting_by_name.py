"""Tests de la Fase 2 del plan A6 — saludo por nombre, guión de conversación.

Cubre `.claude/analysis/plans/20260726-a6-nombre-cliente-saludo.plan.md`:
verifica, sobre el MISMO camino que usan los tests existentes de
`test_orchestrator.py` (`orchestrator.respond`, con `generate_reply`
guionado vía monkeypatch — cero red), que cuando el cliente se presenta el
LLM registra su nombre con `enriquecer_perfil` y el orquestador lo persiste
(`EnrichmentService`) y lo usa en el saludo. También describe (RED) que el
`SYSTEM_PROMPT` debe instruir preguntar el nombre con la frase "con quién
tengo el gusto" al arrancar la conversación — eso todavía no está en el
prompt, así que ese segundo test debe fallar hoy por la razón correcta.

Patrón de engine SQLite in-memory + `init_db` + monkeypatch de
`app.repositories.db.get_engine`: igual que
`tests/test_agent_tools.py::TestEnriquecerPerfil` /
`TestNombreEnConversacion`.
"""

from __future__ import annotations

from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

from app.repositories import db as db_module
from app.repositories.db import init_db
from app.schemas.conversation import ConversationCreate
from app.services.conversation import conversation_service
from app.services.enrichment import EnrichmentService
from app.services.integrations.gemini_client import GeminiReply

import app.services.orchestrator as orchestrator


# -- helpers (mismo patrón que test_orchestrator.py) --------------------------


def _scripted_llm(replies: list[GeminiReply]):
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


def _new_session() -> str:
    session = conversation_service.create(ConversationCreate())
    return session.session_id


def _find_function_response(contents, name: str) -> dict | None:
    for message in contents:
        for part in message.get("parts", []):
            function_response = part.get("functionResponse")
            if function_response and function_response.get("name") == name:
                return function_response
    return None


class TestSaludoPorNombre:
    def setup_method(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        init_db(self.engine)

    def test_cliente_se_presenta_y_es_nombrado(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)

        sid = _new_session()
        llm = _scripted_llm(
            [
                GeminiReply(
                    kind="tool_call",
                    tool_name="enriquecer_perfil",
                    tool_args={"campo": "nombre", "valor": "Carlos"},
                ),
                GeminiReply(
                    kind="text",
                    text="¡Hola, Carlos! Cuéntame, ¿qué quieres proteger hoy?",
                ),
            ]
        )
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        result = orchestrator.respond(sid, "Hola, soy Carlos")

        assert result is not None
        assert len(llm.calls) == 2

        assert EnrichmentService(engine=self.engine).fields_for(sid) == {
            "nombre": "Carlos"
        }

        assert result.messages[-1].role == "assistant"
        assert "Carlos" in result.messages[-1].content

        second_call_contents = llm.calls[1]["contents"]
        function_response = _find_function_response(
            second_call_contents, "enriquecer_perfil"
        )
        assert function_response is not None
        assert function_response["response"]["persistido"] is True

    def test_prompt_instruye_preguntar_nombre(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)

        sid = _new_session()
        llm = _scripted_llm([GeminiReply(kind="text", text="¡Hola! ¿En qué te ayudo?")])
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        orchestrator.respond(sid, "hola")

        assert len(llm.calls) == 1
        system_instruction = llm.calls[0]["system_instruction"]
        assert "con quién tengo el gusto" in system_instruction
