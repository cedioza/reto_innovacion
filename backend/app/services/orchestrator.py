"""Orquestador conversacional del agente de seguros.

Este service ejecuta el loop que conecta al LLM (Gemini, vía
``generate_reply``) con las herramientas de negocio (``agent_tools``) y la
sesión de conversación (``conversation_service``): el LLM decide QUÉ
preguntar y CÓMO explicarlo; los motores deterministas (propensión, cotización,
consentimiento) deciden QUÉ recomendar y A QUÉ PRECIO. El LLM nunca inventa un
precio, una cobertura ni una recomendación — solo los relata a partir de lo
que las tools le devuelven.
"""

from __future__ import annotations

from app.schemas.conversation import (
    ConsentedApplication,
    ConversationResponse,
    ConversationState,
    Message,
    ProfileData,
    QuoteDetail,
    Recommendation,
)
from app.services.agent_tools import ToolContext, execute_tool, tool_declarations
from app.services.catalog import CatalogService
from app.services.conversation import conversation_service
from app.services.integrations.gemini_client import (
    FALLBACK_MESSAGE,
    function_call_part,
    function_response_part,
    generate_reply,
    model_message,
    text_part,
    user_message,
)

MAX_TOOL_ROUNDS = 5

SYSTEM_PROMPT = """\
Eres el asistente virtual de seguros de Colsubsidio: acompañas a las personas \
a proteger su hogar con calidez y cercanía, como se habla en Colombia. Saludas \
con calidez (por su nombre si ya lo sabes), escuchas antes de ofrecer, y \
respondes las objeciones con empatía genuina (p. ej. "Tienes toda la razón, \
entiendo la preocupación, déjame contarte..."). Nunca suenas a formulario ni a \
chatbot frío: conversas.

REGLAS DURAS (nunca las rompas):
1. Los precios, coberturas y recomendaciones SALEN EXCLUSIVAMENTE de las \
herramientas (perfilar_cliente, recomendar_seguro, cotizar, ajustar_comparar, \
cerrar_venta). Jamás inventes, calcules de memoria ni redondees una cifra: \
cita textualmente lo que devuelve la herramienta.
2. Haz como máximo 1 o 2 preguntas por turno; nunca abrumes con un \
cuestionario largo.
3. Cuando expliques una recomendación, usa las razones concretas que devolvió \
la herramienta (evidencia del motor), no justificaciones genéricas.
4. Antes de llamar a cerrar_venta pide el consentimiento explícito del \
cliente ("¿confirmas que quieres dejar tu solicitud lista para pago?") y solo \
entonces invoca la herramienta con ese consentimiento.
5. Si una herramienta devuelve un error, corrige el rumbo en tu siguiente \
turno (por ejemplo, perfila primero al cliente si falta el perfil) en vez de \
insistir con el mismo llamado o inventar una respuesta.
"""


def _ctx_from_session(session_id: str, session: ConversationResponse) -> ToolContext:
    """Construye el `ToolContext` del turno a partir del estado ya persistido."""
    recommendation: dict | None = None
    if session.recommendation is not None:
        recommendation = {
            "product_id": session.recommendation.product_id,
            "reasons": session.recommendation.reasons,
        }

    quote: dict | None = None
    if session.quote is not None:
        quote = session.quote.model_dump()

    return ToolContext(
        session_id=session_id,
        profile=session.profile,
        recommendation=recommendation,
        quote=quote,
    )


def _contents_from_history(session: ConversationResponse) -> list[dict]:
    """Traduce `session.messages` (transcripción user/assistant) a `contents` Gemini."""
    contents: list[dict] = []
    for message in session.messages:
        if message.role == "user":
            contents.append(user_message(text_part(message.content)))
        elif message.role == "assistant":
            contents.append(model_message(text_part(message.content)))
    return contents


def _build_status_summary(ctx: ToolContext) -> str:
    """Resumen de estado del funnel, generado por código (no por el LLM).

    Se inyecta en el system prompt del turno para que el modelo no pierda el
    estado entre turnos, con valores textuales que salen tal cual del motor.
    """
    lines = [
        "Estado actual del funnel para esta sesión (estos datos vienen del "
        "motor, son la única fuente de verdad — nunca los reemplaces):",
    ]

    if ctx.profile is not None:
        campos = ctx.profile.model_dump(exclude_none=True)
        lines.append(f"- Perfil ya capturado: {campos}.")
    else:
        lines.append("- Perfil: aún no capturado.")

    if ctx.recommendation is not None:
        product_id = ctx.recommendation.get("product_id")
        reasons = ctx.recommendation.get("reasons", [])
        lines.append(
            f"- Recomendación vigente: producto '{product_id}', razones: {reasons}."
        )
    else:
        lines.append("- Recomendación: aún no calculada.")

    if ctx.quote is not None:
        monthly = ctx.quote.get("monthly_premium")
        currency = ctx.quote.get("currency", "COP")
        lines.append(f"- Cotización vigente: prima mensual {monthly} {currency}.")
    else:
        lines.append("- Cotización: aún no calculada.")

    return "\n".join(lines)


def _sync_ctx_to_session(
    session: ConversationResponse,
    ctx: ToolContext,
    cerrar_venta_result: dict | None,
) -> None:
    """Vuelca lo que las tools calcularon en `ctx` de vuelta a la sesión."""
    session.profile = ctx.profile

    if ctx.recommendation is not None:
        product_id = ctx.recommendation.get("product_id", "hogar-estandar")
        product = CatalogService().get_product(product_id)
        product_name = product.name if product else "Hogar Estándar"
        session.recommendation = Recommendation(
            product_id=product_id,
            product_name=product_name,
            reasons=ctx.recommendation.get("reasons", []),
        )

    if ctx.quote is not None:
        quote_fields = {
            key: value
            for key, value in ctx.quote.items()
            if key in QuoteDetail.model_fields
        }
        session.quote = QuoteDetail(**quote_fields)
        if session.state in (
            ConversationState.COLLECTING_PROFILE,
            ConversationState.RECOMMENDATION_READY,
        ):
            session.state = ConversationState.QUOTE_READY

    if cerrar_venta_result is not None:
        session.state = ConversationState.READY_FOR_PAYMENT
        session.application = ConsentedApplication(**cerrar_venta_result)


def respond(session_id: str, content: str) -> ConversationResponse | None:
    """Ejecuta un turno completo de conversación libre para `session_id`.

    Devuelve la sesión actualizada, o `None` si `session_id` no existe (sin
    llamar al LLM ni a ninguna tool).
    """
    session = conversation_service.get(session_id)
    if session is None:
        return None

    ctx = _ctx_from_session(session_id, session)
    contents = _contents_from_history(session)
    contents.append(user_message(text_part(content)))

    system_instruction = SYSTEM_PROMPT + "\n\n" + _build_status_summary(ctx)

    texto_final = FALLBACK_MESSAGE
    cerrar_venta_result: dict | None = None

    for _ in range(MAX_TOOL_ROUNDS):
        reply = generate_reply(
            contents,
            tools=tool_declarations(),
            system_instruction=system_instruction,
        )

        if reply.kind == "tool_call":
            resultado = execute_tool(reply.tool_name, reply.tool_args, ctx)
            if reply.tool_name == "cerrar_venta" and "error" not in resultado:
                cerrar_venta_result = resultado
            contents.append(
                model_message(
                    function_call_part(
                        reply.tool_name, reply.tool_args, reply.thought_signature
                    )
                )
            )
            contents.append(
                user_message(function_response_part(reply.tool_name, resultado))
            )
            continue

        if reply.kind == "text":
            texto_final = reply.text
            break

        # reply.kind == "error"
        texto_final = reply.text or FALLBACK_MESSAGE
        break
    else:
        texto_final = FALLBACK_MESSAGE

    _sync_ctx_to_session(session, ctx, cerrar_venta_result)

    session.messages.append(Message(role="user", content=content))
    session.messages.append(Message(role="assistant", content=texto_final))

    conversation_service._repo.save(session.session_id, session)
    return session
