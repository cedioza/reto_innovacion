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

import re

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
    audio_part,
    function_call_part,
    function_response_part,
    generate_reply,
    model_message,
    text_part,
    user_message,
)

MAX_TOOL_ROUNDS = 5

# -- Turnos de audio (A5, Fase 3) --------------------------------------------
#
# Cuando el turno trae una nota de voz, se suma esta regla al
# `system_instruction` y se deshabilitan las tools (`tools=None`) para ese
# turno: el modelo no puede actuar sobre lo que "cree" haber entendido del
# audio sin que el cliente lo confirme primero en texto.
VOICE_TURN_RULE = (
    "Este turno incluye una nota de voz del cliente: resume PRIMERO en "
    "texto lo que entendiste del audio y pide confirmación explícita antes "
    "de actuar. No llames herramientas en este turno."
)

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
cliente ("¿confirmas que quieres dejar tu solicitud lista para pago?") Y su \
correo (ahí le llega el link para finalizar con la aseguradora), y solo \
entonces invoca la herramienta con ambos datos. Cuando cerrar_venta se \
ejecuta con éxito, dile al cliente que revise su correo para finalizar con \
la aseguradora — NUNCA prometas contacto humano ("te contactaremos", "un \
asesor te llamará"): nadie de Colsubsidio ni de la aseguradora llama ni \
escribe proactivamente, el siguiente paso siempre depende de que el cliente \
revise su correo.
5. Si una herramienta devuelve un error, corrige el rumbo en tu siguiente \
turno (por ejemplo, perfila primero al cliente si falta el perfil) en vez de \
insistir con el mismo llamado o inventar una respuesta.
6. Tu alcance es acompañar la elección y compra de seguros de hogar. Si te \
preguntan por siniestros, reclamos, pagos de pólizas existentes o \
renovaciones, explica con calidez que eso lo atienden las líneas de atención \
de Colsubsidio y ofrece seguir con lo que sí puedes hacer. No improvises \
procedimientos ni números de contacto.
7. Si no entiendes lo que el cliente quiso decir, dilo con naturalidad y \
pide que te lo repita de otra forma — nunca actúes sobre una suposición.
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
    """Traduce `session.messages` (transcripción user/assistant) a `contents` Gemini.

    Solo los mensajes de texto plano (`type == "text"`) se traducen: los
    mensajes-tarjeta (`recommendation`/`quote`/`comparison`) son resúmenes
    generados por código para la UI, no transcripción de la conversación, y
    nunca deben reenviarse al LLM.
    """
    contents: list[dict] = []
    for message in session.messages:
        if message.type != "text":
            continue
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


# -- Guard mecánico de precios (A5, Fase 1) ---------------------------------
#
# El LLM nunca debería inventar cifras (regla 1 del SYSTEM_PROMPT), pero un
# prompt es una esperanza, no una garantía: este guard es la versión
# mecánica de esa regla, aplicada por código sobre CADA respuesta de texto
# antes de que llegue al cliente. Ninguna cifra monetaria del texto final
# puede quedar fuera del conjunto de valores que las tools calcularon de
# verdad para esta sesión (`ctx.quote`).

# Cifra con marcador "$" (con o sin espacio tras el símbolo). El número
# admite separadores de miles ("." o ",") en grupos de exactamente 3
# dígitos y, opcionalmente, una parte decimal final de 1-2 dígitos.
_DOLLAR_PATTERN = re.compile(r"\$\s*(\d+(?:[.,]\d{3})*)([.,]\d{1,2})?")

# Cifra sin "$" pero seguida de la palabra "pesos" o "COP" (case-insensitive)
# como marcador monetario explícito.
_WORD_PATTERN = re.compile(
    r"(\d+(?:[.,]\d{3})*)([.,]\d{1,2})?\s*(?:pesos|cop)\b", re.IGNORECASE
)


def _normaliza_cifra(entero: str, decimal: str | None) -> float:
    """Convierte los grupos capturados por los patrones monetarios a `float`.

    `entero` puede traer separadores de miles ("." o ","), que se
    descartan; `decimal`, si existe, trae su propio separador como primer
    carácter (p. ej. ",50") que también se descarta antes de anexarlo como
    parte decimal.
    """
    digitos_enteros = re.sub(r"[.,]", "", entero)
    if decimal:
        digitos_decimales = decimal[1:]
        return float(f"{digitos_enteros}.{digitos_decimales}")
    return float(digitos_enteros)


def _extract_money_figures(texto: str) -> set[float]:
    """Extrae del texto SOLO las cifras con marcador monetario explícito.

    Decisión de diseño: un número sin "$", "pesos" o "COP" nunca dispara el
    guard — así una edad ("35 años"), un estrato ("estrato 3"), un rango
    ("26-40") o una referencia de tiempo ("5 minutos") jamás se confunden
    con un precio. El separador decimal es el ÚLTIMO "."/"," seguido de
    exactamente 1-2 dígitos; cualquier grupo de 3 dígitos tras un "."/","
    se interpreta como separador de miles.
    """
    figuras: set[float] = set()
    for patron in (_DOLLAR_PATTERN, _WORD_PATTERN):
        for match in patron.finditer(texto):
            entero, decimal = match.group(1), match.group(2)
            figuras.add(_normaliza_cifra(entero, decimal))
    return figuras


def _allowed_figures(ctx: ToolContext) -> set[float]:
    """Cifras monetarias con respaldo real: las que ya calculó el motor.

    Sin cotización (`ctx.quote is None`) el conjunto es vacío — sin motor
    que haya calculado nada, ninguna cifra tiene de dónde salir.
    """
    if ctx.quote is None:
        return set()

    campos = ("monthly_premium", "annual_premium", "base_amount")
    return {
        float(ctx.quote[campo])
        for campo in campos
        if ctx.quote.get(campo) is not None
    }


def _plantilla_segura(ctx: ToolContext) -> str:
    """Respuesta de reemplazo cuando el texto del LLM cita una cifra sin respaldo.

    La construye código, no el LLM: con cotización vigente cita la prima
    real que calculó el motor; sin cotización, ninguna cifra en la
    respuesta puede ser real (no hay motor que la haya calculado todavía),
    así que se invita a cotizar en vez de citar cualquier número.
    """
    if ctx.quote is not None and ctx.quote.get("monthly_premium") is not None:
        prima_mensual = _formato_miles(ctx.quote["monthly_premium"])
        return (
            "Para darte solo cifras exactas de nuestra cotización: tu prima "
            f"mensual es de ${prima_mensual} COP. ¿Quieres ajustar coberturas "
            "o seguimos con la compra?"
        )

    return (
        "Prefiero no darte cifras hasta cotizarte con tus datos reales. "
        "¿Te parece si completamos tu perfil y te cotizo con el motor?"
    )


def _formato_miles(monto: float) -> str:
    """Formatea un monto con separador de miles "." (estilo colombiano)."""
    return f"{round(monto):,}".replace(",", ".")


def _guard_reply(texto: str, ctx: ToolContext) -> str:
    """Guard mecánico: intercepta cifras monetarias sin respaldo en las tools.

    Toda cifra monetaria extraída de `texto` debe estar en el conjunto de
    cifras permitidas (`_allowed_figures`); si alguna queda fuera, el texto
    completo se descarta y se reemplaza por la plantilla segura — no se
    intenta "arreglar" la cifra sola, porque el resto de la frase alrededor
    de una cifra inventada tampoco es confiable.
    """
    figuras = _extract_money_figures(texto)
    permitidas = _allowed_figures(ctx)
    if figuras.issubset(permitidas):
        return texto
    return _plantilla_segura(ctx)


def respond(
    session_id: str,
    content: str,
    *,
    audio_data: bytes | None = None,
    audio_mime: str = "audio/ogg",
) -> ConversationResponse | None:
    """Ejecuta un turno completo de conversación libre para `session_id`.

    Si `audio_data` viene informado, el turno es de voz: el mensaje nuevo
    incluye la nota de audio (y el `content` como caption de texto, si no
    viene vacío), se deshabilitan las tools para ese turno (`tools=None`) y
    al `system_instruction` se le suma `VOICE_TURN_RULE`, que pide al modelo
    resumir en texto lo entendido y confirmar antes de actuar — nunca llamar
    herramientas en ese mismo turno. Como defensa en profundidad (por si el
    modelo desobedece la regla), cualquier `tool_call` recibido durante un
    turno de audio se ignora sin ejecutarse: el loop simplemente continúa
    hasta obtener una respuesta de texto. La transcripción que queda en el
    historial de la sesión es el caption si lo hay, o el placeholder
    `"[nota de voz]"` si el turno llegó sin texto.

    El guard mecánico de precios (`_guard_reply`) se sigue aplicando al
    texto final del turno, con o sin audio.

    Devuelve la sesión actualizada, o `None` si `session_id` no existe (sin
    llamar al LLM ni a ninguna tool).
    """
    session = conversation_service.get(session_id)
    if session is None:
        return None

    is_audio_turn = audio_data is not None

    ctx = _ctx_from_session(session_id, session)
    contents = _contents_from_history(session)

    if is_audio_turn:
        if content:
            contents.append(
                user_message(audio_part(audio_data, audio_mime), text_part(content))
            )
        else:
            contents.append(user_message(audio_part(audio_data, audio_mime)))
        transcript = content or "[nota de voz]"
    else:
        contents.append(user_message(text_part(content)))
        transcript = content

    system_instruction = SYSTEM_PROMPT + "\n\n" + _build_status_summary(ctx)
    if is_audio_turn:
        system_instruction += "\n\n" + VOICE_TURN_RULE

    tools = None if is_audio_turn else tool_declarations()

    texto_final = FALLBACK_MESSAGE
    cerrar_venta_result: dict | None = None
    recomendar_seguro_result: dict | None = None
    cotizar_result: dict | None = None
    ajustar_comparar_result: dict | None = None

    for _ in range(MAX_TOOL_ROUNDS):
        reply = generate_reply(
            contents,
            tools=tools,
            system_instruction=system_instruction,
        )

        if reply.kind == "tool_call":
            if is_audio_turn:
                # Defensa en profundidad: aunque el modelo desobedezca la
                # regla de voz (o el turno venga guionado con un tool_call
                # malicioso), un turno de audio jamás ejecuta herramientas.
                continue
            resultado = execute_tool(reply.tool_name, reply.tool_args, ctx)
            if "error" not in resultado:
                if reply.tool_name == "cerrar_venta":
                    cerrar_venta_result = resultado
                elif reply.tool_name == "recomendar_seguro":
                    recomendar_seguro_result = resultado
                elif reply.tool_name == "cotizar":
                    # `resultado` trae un `product_id` extra que el handler
                    # anexa solo para el LLM; la tarjeta usa el dict tal
                    # cual lo calculó el motor (`ctx.quote`), sin esa clave.
                    cotizar_result = dict(ctx.quote) if ctx.quote else None
                elif reply.tool_name == "ajustar_comparar":
                    ajustar_comparar_result = resultado
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
            texto_final = _guard_reply(reply.text, ctx)
            break

        # reply.kind == "error"
        texto_final = reply.text or FALLBACK_MESSAGE
        break
    else:
        texto_final = FALLBACK_MESSAGE

    _sync_ctx_to_session(session, ctx, cerrar_venta_result)

    session.messages.append(Message(role="user", content=transcript))
    session.messages.append(Message(role="assistant", content=texto_final))
    _append_card_messages(
        session,
        recomendar_seguro_result=recomendar_seguro_result,
        cotizar_result=cotizar_result,
        ajustar_comparar_result=ajustar_comparar_result,
        cerrar_venta_result=cerrar_venta_result,
    )

    conversation_service._repo.save(session.session_id, session)
    return session


def _append_card_messages(
    session: ConversationResponse,
    *,
    recomendar_seguro_result: dict | None,
    cotizar_result: dict | None,
    ajustar_comparar_result: dict | None,
    cerrar_venta_result: dict | None = None,
) -> None:
    """Agrega los mensajes-tarjeta del turno, en orden recommendation → quote → comparison → application.

    Solo se emite tarjeta para las tools clave que corrieron con éxito en
    ESTE turno (los resultados llegan `None` si la tool no corrió o falló).
    El `content` de cada tarjeta es un resumen de una línea generado por
    código, nunca por el LLM.
    """
    if recomendar_seguro_result is not None:
        product_id = recomendar_seguro_result.get("product_id", "hogar-estandar")
        product = CatalogService().get_product(product_id)
        product_name = product.name if product else "Hogar Estándar"
        reasons = recomendar_seguro_result.get("reasons", [])
        session.messages.append(
            Message(
                role="assistant",
                type="recommendation",
                content=f"📋 Recomendación: {product_name}",
                payload={
                    "product_id": product_id,
                    "product_name": product_name,
                    "reasons": reasons,
                },
            )
        )

    if cotizar_result is not None:
        monthly = cotizar_result.get("monthly_premium")
        currency = cotizar_result.get("currency", "COP")
        if monthly is not None:
            resumen = f"💰 Cotización: ${_formato_miles(monthly)} {currency}/mes"
        else:
            resumen = "💰 Cotización calculada."
        session.messages.append(
            Message(
                role="assistant",
                type="quote",
                content=resumen,
                payload=cotizar_result,
            )
        )

    if ajustar_comparar_result is not None:
        diferencia = ajustar_comparar_result.get("diferencia_mensual")
        if diferencia is not None:
            signo = "-" if diferencia < 0 else "+"
            resumen = (
                "⚖️ Comparación de opciones: diferencia "
                f"{signo}${_formato_miles(abs(diferencia))} COP/mes"
            )
        else:
            resumen = "⚖️ Comparación de opciones."
        session.messages.append(
            Message(
                role="assistant",
                type="comparison",
                content=resumen,
                payload=ajustar_comparar_result,
            )
        )

    if cerrar_venta_result is not None:
        product_id = cerrar_venta_result.get("product_id", "hogar-estandar")
        product = CatalogService().get_product(product_id)
        product_name = product.name if product else "Hogar Estándar"
        quote = cerrar_venta_result.get("quote") or {}
        session.messages.append(
            Message(
                role="assistant",
                type="application",
                content="🎉 Solicitud lista — pendiente de pago",
                payload={
                    "product_name": product_name,
                    "monthly_premium": quote.get("monthly_premium"),
                    "currency": quote.get("currency", "COP"),
                    "insurer_name": cerrar_venta_result.get("insurer_name"),
                    "email": cerrar_venta_result.get("email"),
                    "consent_timestamp": cerrar_venta_result.get(
                        "consent_timestamp"
                    ),
                },
            )
        )
