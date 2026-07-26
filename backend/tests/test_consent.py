"""Tests for consent service — TDD RED phase."""

import logging

import pytest

from app.core.config import settings
from app.services.consent import ConsentService
from app.services.integrations import resend_client
from app.schemas.conversation import (
    ProfileData,
    Recommendation,
    QuoteDetail,
    ConversationState,
)


class TestConsentService:
    def setup_method(self) -> None:
        self.service = ConsentService()
        self.profile = ProfileData(
            age_range="26-40",
            property_type="house",
            zone="urban",
            stratum=3,
        )
        self.recommendation = Recommendation(
            product_id="hogar-estandar",
            product_name="Hogar Estándar",
            reasons=[{"code": "homeowner", "label": "Propietario", "evidence": "Casa"}],
        )
        self.quote = QuoteDetail(
            base_amount=45000.0,
            monthly_premium=3750.0,
            coverage_details=["Incendio", "Hurto"],
            exclusions=["Guerra"],
        )

    def test_capture_creates_application(self) -> None:
        app = self.service.capture(
            session_id="sess-1",
            product_id="hogar-estandar",
            profile=self.profile,
            recommendation=self.recommendation,
            quote=self.quote,
        )
        assert app.session_id == "sess-1"
        assert app.state == ConversationState.READY_FOR_PAYMENT
        assert app.consent_timestamp is not None

    def test_application_has_all_data(self) -> None:
        app = self.service.capture(
            session_id="sess-2",
            product_id="hogar-estandar",
            profile=self.profile,
            recommendation=self.recommendation,
            quote=self.quote,
        )
        assert app.product_id == "hogar-estandar"
        assert app.profile.age_range == "26-40"
        assert app.recommendation.product_name == "Hogar Estándar"
        assert app.quote.monthly_premium == 3750.0

    def test_get_application_after_capture(self) -> None:
        self.service.capture(
            session_id="sess-3",
            product_id="hogar-estandar",
            profile=self.profile,
            recommendation=self.recommendation,
            quote=self.quote,
        )
        app = self.service.get_application("sess-3")
        assert app is not None
        assert app.session_id == "sess-3"

    def test_get_nonexistent_returns_none(self) -> None:
        app = self.service.get_application("no-existe")
        assert app is None

    # -- list_applications (plan G4, Fase 2) ----------------------------------
    #
    # Delegación directa al `ApplicationRepository.list_all()` subyacente.

    def test_list_applications_delegates_to_repository(self) -> None:
        self.service.capture(
            session_id="sess-list-1",
            product_id="hogar-estandar",
            profile=self.profile,
            recommendation=self.recommendation,
            quote=self.quote,
        )

        apps = self.service.list_applications()

        session_ids = [app.session_id for app in apps]
        assert "sess-list-1" in session_ids


# ---------------------------------------------------------------------------
# Guard de FRONTEND_URL en despliegue (plan E7, Fase 2) — TDD RED.
#
# Bug: el correo de handoff arma su link con `settings.frontend_url`, cuyo
# default es "http://localhost:5173". Si un backend DESPLEGADO (señal:
# `settings.backend_public_url` no vacía, hoy solo se configura en
# producción para el webhook de Telegram) envía el correo sin `FRONTEND_URL`
# configurada, el cliente recibe un botón que apunta a localhost — muerto.
#
# `ConsentService.capture()` debe detectar esa combinación inconsistente
# justo antes de construir/enviar el correo de handoff, evitar el envío y
# loguear un error explícito, sin romper el resto del cierre (la
# `ConsentedApplication` se crea y persiste igual). Este guard aún no existe
# en `app/services/consent.py`: estos tests deben fallar en rojo.
# ---------------------------------------------------------------------------


class TestConsentServiceFrontendUrlGuard:
    def setup_method(self) -> None:
        self.service = ConsentService()
        self.profile = ProfileData(
            age_range="26-40",
            property_type="house",
            zone="urban",
            stratum=3,
        )
        self.recommendation = Recommendation(
            product_id="hogar-estandar",
            product_name="Hogar Estándar",
            reasons=[{"code": "homeowner", "label": "Propietario", "evidence": "Casa"}],
        )
        self.quote = QuoteDetail(
            base_amount=45000.0,
            monthly_premium=3750.0,
            coverage_details=["Incendio", "Hurto"],
            exclusions=["Guerra"],
        )

    def test_deployed_backend_with_localhost_frontend_skips_email_and_logs_error(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(
            settings, "backend_public_url", "https://api.colsubsidio.zyvra.lat"
        )
        monkeypatch.setattr(settings, "frontend_url", "http://localhost:5173")

        called: list = []

        def _fake_send_email(*args, **kwargs) -> dict:
            called.append((args, kwargs))
            return {"ok": True, "id": "re_test"}

        monkeypatch.setattr(resend_client, "send_email", _fake_send_email)

        with caplog.at_level(logging.ERROR, logger="app.services.consent"):
            app = self.service.capture(
                session_id="sess-e7-guard-1",
                product_id="hogar-estandar",
                profile=self.profile,
                recommendation=self.recommendation,
                quote=self.quote,
                email="cliente@example.com",
            )

        assert called == []
        assert any("FRONTEND_URL" in record.message for record in caplog.records)

        # El cierre sigue intacto pese al correo omitido.
        assert app.handoff_token is not None
        assert app.state == ConversationState.READY_FOR_PAYMENT
        persisted = self.service.get_application("sess-e7-guard-1")
        assert persisted is not None
        assert persisted.handoff_token == app.handoff_token

    def test_deployed_backend_with_127_0_0_1_frontend_skips_email(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(
            settings, "backend_public_url", "https://api.colsubsidio.zyvra.lat"
        )
        monkeypatch.setattr(settings, "frontend_url", "http://127.0.0.1:5173")

        called: list = []

        def _fake_send_email(*args, **kwargs) -> dict:
            called.append((args, kwargs))
            return {"ok": True, "id": "re_test"}

        monkeypatch.setattr(resend_client, "send_email", _fake_send_email)

        with caplog.at_level(logging.ERROR, logger="app.services.consent"):
            self.service.capture(
                session_id="sess-e7-guard-2",
                product_id="hogar-estandar",
                profile=self.profile,
                recommendation=self.recommendation,
                quote=self.quote,
                email="cliente@example.com",
            )

        assert called == []
        assert any("FRONTEND_URL" in record.message for record in caplog.records)

    def test_deployed_backend_with_real_frontend_domain_sends_email(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            settings, "backend_public_url", "https://api.colsubsidio.zyvra.lat"
        )
        monkeypatch.setattr(
            settings, "frontend_url", "https://colsubsidio.zyvra.lat"
        )

        called: list = []

        def _fake_send_email(email: str, subject: str, html: str) -> dict:
            called.append({"email": email, "subject": subject, "html": html})
            return {"ok": True, "id": "re_fake"}

        monkeypatch.setattr(resend_client, "send_email", _fake_send_email)

        app = self.service.capture(
            session_id="sess-e7-guard-3",
            product_id="hogar-estandar",
            profile=self.profile,
            recommendation=self.recommendation,
            quote=self.quote,
            email="cliente@example.com",
        )

        assert len(called) == 1
        sent_html = called[0]["html"]
        assert f"https://colsubsidio.zyvra.lat/aseguradora/{app.handoff_token}" in sent_html

    def test_local_dev_with_localhost_frontend_still_sends_email(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "backend_public_url", "")
        monkeypatch.setattr(settings, "frontend_url", "http://localhost:5173")

        called: list = []

        def _fake_send_email(email: str, subject: str, html: str) -> dict:
            called.append({"email": email, "subject": subject, "html": html})
            return {"ok": True, "id": "re_fake"}

        monkeypatch.setattr(resend_client, "send_email", _fake_send_email)

        app = self.service.capture(
            session_id="sess-e7-guard-4",
            product_id="hogar-estandar",
            profile=self.profile,
            recommendation=self.recommendation,
            quote=self.quote,
            email="cliente@example.com",
        )

        assert len(called) == 1
        sent_html = called[0]["html"]
        assert f"http://localhost:5173/aseguradora/{app.handoff_token}" in sent_html
