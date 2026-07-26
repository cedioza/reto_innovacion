"""Tests for the demo data seeder (`app.scripts.seed_demo`).

Corren contra SQLite in-memory (mismo patrón que
`test_conversation_repository.py` / `test_applications_repository.py`):
engine `StaticPool` fresco por test, con `app.repositories.db.get_engine`
parcheado para que apunte a ese engine. Esto es necesario porque
`ConsentService` (usado internamente por `sembrar`) resuelve su
`ApplicationRepository` sin pasar un engine explícito, así que siempre cae al
engine global — parchear `get_engine` es la única forma de interceptarlo.

Nota: al momento de escribir esta suite `app.scripts.seed_demo` todavía no
existe, así que el archivo completo falla en colección con
`ModuleNotFoundError` — es la razón correcta de fallo hasta que la siguiente
tarea implemente el módulo.
"""

from __future__ import annotations

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from app.models.conversation import ConversationRecord
from app.repositories import db as db_module
from app.repositories.applications import ApplicationRepository
from app.repositories.conversations import ConversationRepository
from app.repositories.db import init_db
from app.schemas.conversation import (
    ConsentedApplication,
    ConversationResponse,
    ConversationState,
    Message,
)
from app.scripts.seed_demo import SEED_PREFIX, main, sembrar
from app.services.integrations import resend_client
from app.services.propensity import PropensityService

VENTAS_IDS = [
    "seed-demo-hogar",
    "seed-demo-vida",
    "seed-demo-accidentes",
    "seed-demo-movilidad",
    "seed-demo-credito",
]

EN_CURSO_ESTADOS = {
    "seed-demo-en-curso-1": ConversationState.QUOTE_READY,
    "seed-demo-en-curso-2": ConversationState.AWAITING_CONSENT,
}


@pytest.fixture()
def engine(monkeypatch):
    """Engine SQLite in-memory aislado por test, inyectado como engine global.

    `ConsentService`/`ApplicationRepository`/`ConversationRepository`
    instanciados sin `engine` explícito resuelven vía
    `app.repositories.db.get_engine()`; parchearlo asegura que TODO el
    trabajo de `sembrar`/`main` (incluido el capture de consentimiento) caiga
    sobre este mismo engine de test, nunca sobre el SQLite en disco de
    desarrollo.
    """
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(test_engine)
    monkeypatch.setattr(db_module, "get_engine", lambda: test_engine)
    return test_engine


class TestSeedDemo:
    def test_siembra_conteos_y_estados(self, engine) -> None:
        resumen = sembrar()

        assert resumen["conversaciones"] == 7
        assert resumen["solicitudes"] == 5
        assert all(sid.startswith(SEED_PREFIX) for sid in resumen["ids"])

        conv_repo = ConversationRepository(engine=engine)
        app_repo = ApplicationRepository(engine=engine)

        for sid in VENTAS_IDS:
            conv = conv_repo.find(sid)
            assert conv is not None
            assert conv.state == ConversationState.FINALIZED_DEMO
            assert app_repo.find(sid) is not None

        for sid, estado_esperado in EN_CURSO_ESTADOS.items():
            conv = conv_repo.find(sid)
            assert conv is not None
            assert conv.state == estado_esperado
            assert app_repo.find(sid) is None

    def test_venta_roundtrip_valido(self, engine) -> None:
        sembrar()

        app_repo = ApplicationRepository(engine=engine)
        conv_repo = ConversationRepository(engine=engine)

        solicitud = app_repo.find("seed-demo-hogar")
        assert solicitud is not None
        assert isinstance(solicitud, ConsentedApplication)
        assert solicitud.handoff_token
        assert solicitud.insurer_name
        assert solicitud.quote.monthly_premium > 0
        assert solicitud.state == ConversationState.FINALIZED_DEMO

        conv = conv_repo.find("seed-demo-hogar")
        assert conv is not None
        assert conv.state == ConversationState.FINALIZED_DEMO
        assert conv.application is not None
        assert conv.application.session_id == "seed-demo-hogar"
        assert conv.recommendation is not None
        assert conv.recommendation.product_id == solicitud.recommendation.product_id

    def test_recomendacion_coherente_con_motor(self, engine) -> None:
        sembrar()

        conv_repo = ConversationRepository(engine=engine)
        service = PropensityService()

        for sid in VENTAS_IDS:
            conv = conv_repo.find(sid)
            assert conv is not None
            assert conv.profile is not None
            assert conv.recommendation is not None

            resultado = service.evaluate(conv.profile)

            assert resultado["ranking"][0]["product_id"] == conv.recommendation.product_id

    def test_mensajes_con_timestamp(self, engine) -> None:
        resumen = sembrar()

        conv_repo = ConversationRepository(engine=engine)

        for sid in resumen["ids"]:
            conv = conv_repo.find(sid)
            assert conv is not None
            assert 4 <= len(conv.messages) <= 6
            assert all(m.timestamp is not None for m in conv.messages)
            roles = {m.role for m in conv.messages}
            assert "user" in roles
            assert "assistant" in roles

    def test_created_at_escalonados(self, engine) -> None:
        resumen = sembrar()

        with Session(engine) as session:
            statement = select(ConversationRecord).where(
                ConversationRecord.session_id.in_(resumen["ids"])
            )
            records = session.exec(statement).all()

        assert len(records) == 7
        created_ats = {record.created_at for record in records}
        assert len(created_ats) > 1

    def test_sin_replace_aborta_sin_tocar(self, engine) -> None:
        sembrar()

        conv_repo = ConversationRepository(engine=engine)
        app_repo = ApplicationRepository(engine=engine)
        conversaciones_antes = conv_repo.count()
        solicitudes_antes = app_repo.count()

        with pytest.raises(RuntimeError):
            sembrar()

        assert conv_repo.count() == conversaciones_antes
        assert app_repo.count() == solicitudes_antes

    def test_replace_idempotente_y_no_toca_reales(self, engine) -> None:
        conv_repo = ConversationRepository(engine=engine)
        real = ConversationResponse(
            session_id="real-xyz",
            state=ConversationState.COLLECTING_PROFILE,
            messages=[Message(role="user", content="Hola, soy un afiliado real")],
            next_action="Cuéntame sobre tu hogar",
        )
        conv_repo.save(real.session_id, real)

        sembrar()
        sembrar(replace=True)

        app_repo = ApplicationRepository(engine=engine)
        assert conv_repo.count() == 8  # 7 sembrados + 1 real, sin duplicados
        assert app_repo.count() == 5

        encontrada = conv_repo.find("real-xyz")
        assert encontrada is not None
        assert encontrada.state == ConversationState.COLLECTING_PROFILE
        assert encontrada.messages[0].content == "Hola, soy un afiliado real"

    def test_no_dispara_correo(self, engine, monkeypatch) -> None:
        def _boom(*args, **kwargs):
            raise AssertionError(
                "sembrar() no debería disparar envío de correo (email=None)"
            )

        monkeypatch.setattr(resend_client, "send_email", _boom)

        sembrar()  # no debe lanzar

    def test_cli_replace_ok_y_sin_replace_falla(self, engine, capsys) -> None:
        main(["--replace"])
        salida = capsys.readouterr().out
        assert "7" in salida

        with pytest.raises(SystemExit) as exc_info:
            main([])

        assert exc_info.value.code != 0
