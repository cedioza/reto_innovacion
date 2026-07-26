import re

from sqlalchemy import Engine

from app.repositories.channel_sessions import ChannelSessionRepository
from app.schemas.conversation import (
    ConversationCreate,
    ConversationState,
    ProfileData,
)
from app.services.conversation import ConversationService, conversation_service

AFFIRMATIVE = {"si", "sí", "acepto", "ok", "dale", "confirmo", "consiento", "claro", "dale"}
AGE_PATTERNS = [
    (r"18\s*(?:-|a)\s*25", "18-25"),
    (r"26\s*(?:-|a)\s*35", "26-35"),
    (r"30\s*(?:-|a)\s*40", "30-40"),
    (r"36\s*(?:-|a)\s*45", "36-45"),
    (r"46\s*(?:-|a)\s*60", "46-60"),
    (r"60\s*[+]", "60+"),
    (r"adulto\s*mayor", "60+"),
    (r"joven", "18-25"),
    (r"adulto", "36-45"),
]

WELCOME_TEXT = (
    "¡Hola! Soy el asistente de seguros de Colsubsidio 🏠\n\n"
    "Te voy a ayudar a cotizar tu seguro de hogar en pocos pasos."
)

PROFILE_PROMPT = (
    "Para darte una cotización necesito algunos datos. "
    "Respondeme en este formato:\n\n"
    "*edad* (18-25, 26-35, 36-45, 46-60, 60+)\n"
    "*estrato* (1-6)\n"
    "*propiedad* (casa / apartamento)\n"
    "*zona* (urbana / rural)\n"
    "*propietario* (si / no)\n"
    "*valor aprox* (en pesos)\n"
    "*familia* (si / no)\n"
    "*alarma incendio* (si / no)\n"
    "*cámaras* (si / no)\n\n"
    "Ej: 30-40, 4, apartamento, urbana, si, 200000000, si, si, no"
)

PARSE_FAIL_TEXT = (
    "No entendí bien los datos. "
    "Por favor respondeme siguiendo este formato:\n\n"
    "*edad*, *estrato*, *propiedad*, *zona*, *propietario*, *valor*, *familia*, *alarma*, *cámaras*\n\n"
    "Ej: 30-40, 4, apartamento, urbana, si, 200000000, si, si, no"
)

DONE_TEXT = (
    "✅ ¡Listo! Tu solicitud de Hogar Estándar quedó registrada y lista para "
    "pago. Gracias por confiar en Colsubsidio 🎉"
)

CONSENT_PROMPT = (
    "Perfecto. Para generar la solicitud necesito tu consentimiento. "
    "¿Confirmás que entendés las coberturas y exclusiones "
    "y querés dejar tu solicitud lista para pago? "
    "Respondé *consiento* o *si* para continuar."
)

REJECT_TEXT = (
    "Entendido. No hay problema, si en otro momento querés retomar "
    "la solicitud solo escribime. ¡Estoy acá para ayudarte!"
)

READY_TEXT = (
    "Tu solicitud ya está lista para pago. "
    "Tu comprobante queda registrado en el sistema."
)


class ChannelHandler:
    def __init__(
        self,
        service: ConversationService | None = None,
        engine: Engine | None = None,
    ) -> None:
        self._service = service or conversation_service
        self._sessions_repo = ChannelSessionRepository(engine=engine)
        # `_pending_field` se queda en memoria: es estado efímero de UX (qué
        # campo del perfil se está pidiendo); su pérdida en un redeploy es
        # inocua, el usuario simplemente vuelve a ver el prompt del perfil.
        self._pending_field: dict[str, str | None] = {}

    def handle_incoming(self, channel: str, user_id: str, text: str) -> str:
        text_clean = text.strip().lower()

        session_id = self._sessions_repo.find(channel, user_id)

        if session_id is None:
            session = self._service.create(ConversationCreate())
            self._sessions_repo.save(channel, user_id, session.session_id)
            self._pending_field[session.session_id] = "profile"
            return f"{WELCOME_TEXT}\n\n{PROFILE_PROMPT}"

        session = self._service.get(session_id)
        if session is None:
            self._pending_field.pop(session_id, None)
            new_session = self._service.create(ConversationCreate())
            self._sessions_repo.save(channel, user_id, new_session.session_id)
            self._pending_field[new_session.session_id] = "profile"
            return f"{WELCOME_TEXT}\n\n{PROFILE_PROMPT}"

        state = session.state

        if state == ConversationState.COLLECTING_PROFILE:
            return self._handle_collecting_profile(session_id, text_clean, session)

        if state == ConversationState.QUOTE_READY:
            return self._handle_quote_ready(session_id, text_clean, session)

        if state == ConversationState.AWAITING_CONSENT:
            return self._handle_awaiting_consent(session_id, text_clean, session)

        if state == ConversationState.READY_FOR_PAYMENT:
            return READY_TEXT

        return PROFILE_PROMPT

    def was_event_processed(self, event_id: str) -> bool:
        """Expone la deduplicación de eventos de webhook al router (que no
        puede tocar un repository directamente, ver reglas de capas)."""
        return self._sessions_repo.is_event_processed(event_id)

    def mark_event_processed(self, event_id: str) -> bool:
        """Ídem, para marcar un evento como procesado tras entrega exitosa."""
        return self._sessions_repo.mark_event_processed(event_id)

    def _handle_collecting_profile(
        self, session_id: str, text_clean: str, session
    ) -> str:
        pending = self._pending_field.get(session_id)
        if pending is None:
            profile, error = self._parse_profile(text_clean)
            if error:
                return error
        else:
            profile, error = self._parse_profile(text_clean)
            if error:
                return error

        if profile is None:
            return PARSE_FAIL_TEXT

        self._pending_field[session_id] = None

        try:
            result = self._service.update_profile(session_id, profile)
        except ValueError as exc:
            return str(exc)

        quote = result.quote
        lines = [
            "✅ ¡Datos registrados!",
            "",
            f"*Producto recomendado:* {result.recommendation.product_name}",
            f"*Prima mensual estimada:* ${quote.monthly_premium:,.0f} COP",
            "",
            "*Coberturas incluidas:*",
        ]
        for c in quote.coverage_details:
            lines.append(f"  • {c}")
        lines.extend([
            "",
            "*Exclusiones principales:*",
        ])
        for e in quote.exclusions:
            lines.append(f"  • {e}")
        lines.extend([
            "",
            "¿Querés aceptar esta cotización? Respondé *acepto* o *si* para continuar.",
        ])
        return "\n".join(lines)

    def _handle_quote_ready(
        self, session_id: str, text_clean: str, session
    ) -> str:
        if any(word in text_clean for word in AFFIRMATIVE):
            try:
                self._service.accept_quote(session_id)
            except ValueError as exc:
                return str(exc)
            return CONSENT_PROMPT

        quote = session.quote
        lines = [
            f"*Producto:* {session.recommendation.product_name}",
            f"*Prima mensual:* ${quote.monthly_premium:,.0f} COP",
            "",
            "*Coberturas:*",
        ]
        for c in quote.coverage_details:
            lines.append(f"  • {c}")
        lines.extend([
            "",
            "¿Querés aceptar esta cotización? Respondé *acepto* o *si* para continuar.",
        ])
        return "\n".join(lines)

    def _handle_awaiting_consent(
        self, session_id: str, text_clean: str, session
    ) -> str:
        if any(word in text_clean for word in AFFIRMATIVE):
            try:
                self._service.submit_consent(session_id, True)
            except ValueError as exc:
                return str(exc)
            return DONE_TEXT

        return REJECT_TEXT

    def _parse_profile(self, text: str) -> tuple[ProfileData | None, str | None]:
        parts = [p.strip() for p in text.split(",")]

        age_range = None
        stratum = None
        property_type = None
        zone = None
        has_family = None

        if len(parts) >= 9:
            age_range = self._match_age(parts[0])
            stratum = self._match_stratum(parts[1])
            property_type = self._match_property(parts[2])
            zone = self._match_zone(parts[3])
            has_family = self._match_yes_no(parts[6])

        if age_range is None:
            age_range = self._match_age(text)
        if stratum is None:
            stratum = self._match_stratum(text)
        if property_type is None:
            property_type = self._match_property(text)
        if zone is None:
            zone = self._match_zone(text)
        if has_family is None:
            has_family = self._match_yes_no(text)

        if age_range is None and stratum is None and property_type is None:
            return None, None

        return ProfileData(
            age_range=age_range,
            stratum=stratum,
            property_type=property_type,
            zone=zone,
            has_family=has_family,
        ), None

    def _match_age(self, text: str) -> str | None:
        t = text.lower().strip()
        for pattern, value in AGE_PATTERNS:
            if re.search(pattern, t):
                return value
        m = re.search(r"(\d{2})", t)
        if m:
            age = int(m.group(1))
            if age <= 25:
                return "18-25"
            elif age <= 35:
                return "26-35"
            elif age <= 45:
                return "36-45"
            elif age <= 60:
                return "46-60"
            else:
                return "60+"
        return None

    def _match_stratum(self, text: str) -> int | None:
        t = text.lower().strip()
        m = re.search(r"(?:estrato|nivel|estrato\s*socioecon[oó]mico)\s*(\d)", t)
        if m:
            val = int(m.group(1))
            if 1 <= val <= 6:
                return val
        m = re.search(r"\b([1-6])\b", t)
        if m:
            return int(m.group(1))
        return None

    def _match_property(self, text: str) -> str | None:
        t = text.lower().strip()
        if any(w in t for w in ("apartamento", "apto", "departamento", "apart")):
            return "apartamento"
        if "casa" in t:
            return "casa"
        return None

    def _match_zone(self, text: str) -> str | None:
        t = text.lower().strip()
        if any(w in t for w in ("urbana", "urbano", "ciudad")):
            return "urbana"
        if any(w in t for w in ("rural", "campo", "vereda")):
            return "rural"
        return None

    def _match_yes_no(self, text: str) -> bool | None:
        t = text.lower().strip()
        if any(w in t for w in ("si", "sí", "true", "hijos", "familia")):
            return True
        if any(w in t for w in ("no", "false", "ninguno", "ninguna")):
            return False
        return None
