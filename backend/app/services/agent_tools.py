"""Contrato de herramientas (tools) del agente conversacional.

Cada tool que el LLM (Gemini function calling) puede invocar se define en dos
partes:

- ``declaration``: el JSON-schema en formato Gemini (``name``/``description``/
  ``parameters``) que se envía tal cual a ``generate_reply(tools=...)``. Es lo
  único que el modelo "ve".
- ``handler``: la función Python que ejecuta la tool contra los services reales
  del backend (nunca repositorios) y devuelve un resultado serializable
  (JSON-safe) que se le reporta de vuelta al LLM.

Regla de diseño central — el estado del funnel NO viaja por el LLM:
``ToolContext`` es el estado calculado del funnel (perfil resuelto,
recomendación, cotización) y **lo posee el código**, nunca el modelo. Los
``args`` de cada tool call solo contienen lo que el cliente declaró en la
conversación (documento, datos del hogar, ajustes elegidos, consentimiento);
cualquier precio, perfil o recomendación ya calculado se lee/escribe en
``ToolContext`` desde el handler, jamás se le pide al LLM que lo repita o lo
reenvíe. Esto es deliberado: en un producto financiero, un precio o perfil que
saliera de la generación libre del modelo (y pudiera ser alterado por un
prompt) es descalificatorio — los datos de productos/precios siempre los
calcula el motor determinista del backend.

``execute_tool`` nunca propaga excepciones al loop del LLM: un nombre de tool
desconocido, un contexto insuficiente (p. ej. faltan pasos previos del
funnel) o un error inesperado del handler siempre se traducen a un dict de
error controlado (``{"error": ..., "detail": ...}``) para que el modelo pueda
corregir el rumbo en el siguiente turno.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from app.schemas.conversation import ProfileData, QuoteDetail, Recommendation
from app.services.affiliate import AffiliateService
from app.services.catalog import CatalogService
from app.services.consent import consent_service
from app.services.propensity import PropensityService
from app.services.quote import QuoteService


@dataclass
class ToolContext:
    """Estado del funnel que las tools leen/escriben.

    Lo posee el código (no el LLM): se crea y persiste por sesión, y cada
    handler lo actualiza con lo que va calculando el motor correspondiente.
    """

    session_id: str = ""
    profile: ProfileData | None = None
    recommendation: dict | None = None
    quote: dict | None = None


@dataclass
class AgentTool:
    """Una tool del agente: su declaración Gemini y su handler Python."""

    declaration: dict[str, Any]
    handler: Callable[[dict[str, Any], ToolContext], dict[str, Any]]


# -- perfilar_cliente ----------------------------------------------------------

_PERFILAR_CLIENTE_DECLARATION: dict[str, Any] = {
    "name": "perfilar_cliente",
    "description": (
        "Busca al cliente en la base de afiliados por su número de documento. "
        "Si el documento no existe en la base (o no se entrega), construye su "
        "perfil con lo que el cliente haya declarado en la conversación "
        "(hogar: tipo de propiedad, zona, estrato, rango de edad, si tiene "
        "familia; y otras señales: si tiene hijos, si tiene vehículo, si "
        "tiene un crédito vigente). Devuelve si es afiliado, la fuente del "
        "perfil ('base' o 'declarado') y el perfil resuelto."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "document_number": {
                "type": "string",
                "description": "Número de documento (cédula) del cliente.",
            },
            "property_type": {
                "type": "string",
                "enum": ["house", "apartment", "other"],
                "description": "Tipo de propiedad declarada por el cliente.",
            },
            "zone": {
                "type": "string",
                "enum": ["urban", "rural"],
                "description": "Zona declarada donde vive el cliente.",
            },
            "stratum": {
                "type": "integer",
                "description": "Estrato socioeconómico declarado (1-6).",
            },
            "age_range": {
                "type": "string",
                "description": "Rango de edad declarado, p. ej. '26-40'.",
            },
            "has_family": {
                "type": "boolean",
                "description": "Si el cliente declara tener familia a cargo.",
            },
            "has_children": {
                "type": "boolean",
                "description": (
                    "Si el cliente declara tener hijos o dependientes a "
                    "cargo."
                ),
            },
            "has_vehicle": {
                "type": "boolean",
                "description": "Si el cliente declara tener carro o moto propios.",
            },
            "has_credit": {
                "type": "boolean",
                "description": (
                    "Si el cliente declara tener un crédito vigente "
                    "(hipotecario, libre inversión, etc.)."
                ),
            },
        },
    },
}


def _perfilar_cliente(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    document_number = args.get("document_number")
    declared = ProfileData(
        property_type=args.get("property_type"),
        zone=args.get("zone"),
        stratum=args.get("stratum"),
        age_range=args.get("age_range"),
        has_family=args.get("has_family"),
        has_children=args.get("has_children"),
        has_vehicle=args.get("has_vehicle"),
        has_credit=args.get("has_credit"),
    )
    has_declared_data = any(
        value is not None
        for value in (
            declared.property_type,
            declared.zone,
            declared.stratum,
            declared.age_range,
            declared.has_family,
            declared.has_children,
            declared.has_vehicle,
            declared.has_credit,
        )
    )

    service = AffiliateService()
    found_affiliate = (
        service.lookup(document_number) if document_number else None
    )
    afiliado = found_affiliate is not None
    fuente = "base" if afiliado else "declarado"

    resolved = service.resolve(
        document_number, declared if has_declared_data else None
    )

    profile = ProfileData(
        property_type=resolved.property_type,
        zone=resolved.zone,
        stratum=resolved.stratum,
        age_range=resolved.age_range,
        has_family=declared.has_family,
        has_children=declared.has_children,
        has_vehicle=declared.has_vehicle,
        has_credit=declared.has_credit,
    )
    ctx.profile = profile

    return {
        "afiliado": afiliado,
        "fuente": fuente,
        "profile": profile.model_dump(),
    }


# -- recomendar_seguro ----------------------------------------------------------

_RECOMENDAR_SEGURO_DECLARATION: dict[str, Any] = {
    "name": "recomendar_seguro",
    "description": (
        "Evalúa la propensión del perfil del cliente (ya obtenido con "
        "perfilar_cliente) usando el motor de reglas explicable y devuelve "
        "el producto recomendado junto con las razones que sustentan la "
        "recomendación."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
    },
}


def _sin_perfil_error() -> dict[str, Any]:
    return {
        "error": "falta el perfil del cliente",
        "detail": "perfila primero al cliente con perfilar_cliente",
    }


def _recomendar_seguro(
    args: dict[str, Any], ctx: ToolContext
) -> dict[str, Any]:
    if ctx.profile is None:
        return _sin_perfil_error()

    result = PropensityService().evaluate(ctx.profile)
    ctx.recommendation = result
    return result


# -- cotizar -----------------------------------------------------------------

_COTIZAR_DECLARATION: dict[str, Any] = {
    "name": "cotizar",
    "description": (
        "Calcula la prima del producto recomendado por el motor de "
        "propensión (recomendar_seguro) con el motor determinista de "
        "tarifas del catálogo, a partir del perfil del cliente ya obtenido "
        "con perfilar_cliente. El precio siempre sale del motor, nunca se "
        "inventa."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "adjustments": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Códigos de ajustes opcionales del catálogo.",
            },
        },
    },
}


def _cotizar(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    if ctx.profile is None:
        return _sin_perfil_error()

    product_id = (ctx.recommendation or {}).get("product_id", "hogar-estandar")
    adjustments = args.get("adjustments") or []
    result = QuoteService().calculate_quote(
        ctx.profile, adjustments, product_id=product_id
    )
    ctx.quote = result
    return {**result, "product_id": product_id}


# -- ajustar_comparar --------------------------------------------------------

_AJUSTAR_COMPARAR_DECLARATION: dict[str, Any] = {
    "name": "ajustar_comparar",
    "description": (
        "Recalcula la cotización aplicando otros ajustes del catálogo y la "
        "compara contra la cotización actual del cliente. Úsala cuando el "
        "cliente quiera ajustar coberturas, comparar opciones o resolver "
        "dudas sobre el precio antes de decidir."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "adjustments": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Códigos de ajustes del catálogo a aplicar en la nueva "
                    "propuesta."
                ),
            },
        },
    },
}


def _sin_cotizacion_error() -> dict[str, Any]:
    return {
        "error": "falta la cotización",
        "detail": "falta la cotización — llama cotizar primero",
    }


def _sin_recomendacion_error() -> dict[str, Any]:
    return {
        "error": "falta la recomendación",
        "detail": "falta la recomendación — llama recomendar_seguro primero",
    }


def _ajustar_comparar(
    args: dict[str, Any], ctx: ToolContext
) -> dict[str, Any]:
    if ctx.profile is None:
        return _sin_perfil_error()
    if ctx.quote is None:
        return _sin_cotizacion_error()

    product_id = (ctx.recommendation or {}).get("product_id", "hogar-estandar")
    adjustments_a = [a["code"] for a in (ctx.quote.get("adjustments") or [])]
    adjustments_b = args.get("adjustments") or []

    result = QuoteService().compare(
        ctx.profile, product_id, adjustments_a, adjustments_b
    )

    ctx.quote = result["propuesta"]

    return result


# -- cerrar_venta -------------------------------------------------------------

_CERRAR_VENTA_DECLARATION: dict[str, Any] = {
    "name": "cerrar_venta",
    "description": (
        "Cierra la venta con el consentimiento explícito del cliente y deja "
        "la solicitud lista para pago. Requiere que el perfil, la "
        "recomendación y la cotización ya se hayan calculado."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "consentimiento": {
                "type": "boolean",
                "description": (
                    "Consentimiento explícito del cliente para cerrar la "
                    "venta. Debe ser true."
                ),
            },
            "email": {
                "type": "string",
                "description": (
                    "Correo del cliente para enviarle el link de cierre."
                ),
            },
        },
        "required": ["consentimiento", "email"],
    },
}

_EMAIL_RE = re.compile(r"^\S+@\S+\.\S+$")


def _correo_invalido_error() -> dict[str, Any]:
    return {
        "error": "falta el correo del cliente",
        "detail": "pide al cliente su correo para enviarle el link de cierre",
    }


def _cerrar_venta(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    if args.get("consentimiento") is not True:
        return {
            "error": "consentimiento requerido",
            "detail": (
                "el consentimiento explícito del cliente es obligatorio "
                "para cerrar la venta"
            ),
        }

    if ctx.profile is None:
        return _sin_perfil_error()
    if ctx.quote is None:
        return _sin_cotizacion_error()
    if ctx.recommendation is None:
        return _sin_recomendacion_error()

    email = args.get("email")
    if not email or not _EMAIL_RE.match(email):
        return _correo_invalido_error()

    product_id = ctx.recommendation.get("product_id", "hogar-estandar")
    product = CatalogService().get_product(product_id)
    product_name = product.name if product else "Hogar Estándar"

    recommendation = Recommendation(
        product_id=product_id,
        product_name=product_name,
        reasons=ctx.recommendation.get("reasons", []),
    )

    quote = QuoteDetail(
        currency=ctx.quote.get("currency", "COP"),
        base_amount=ctx.quote["base_amount"],
        adjustments=ctx.quote.get("adjustments", []),
        monthly_premium=ctx.quote["monthly_premium"],
        coverage_details=ctx.quote.get("coverage_details", []),
        exclusions=ctx.quote.get("exclusions", []),
    )

    application = consent_service.capture(
        session_id=ctx.session_id,
        product_id=product_id,
        profile=ctx.profile,
        recommendation=recommendation,
        quote=quote,
        email=email,
    )

    return application.model_dump(mode="json")


# -- registro --------------------------------------------------------------

AGENT_TOOLS: dict[str, AgentTool] = {
    "perfilar_cliente": AgentTool(
        declaration=_PERFILAR_CLIENTE_DECLARATION,
        handler=_perfilar_cliente,
    ),
    "recomendar_seguro": AgentTool(
        declaration=_RECOMENDAR_SEGURO_DECLARATION,
        handler=_recomendar_seguro,
    ),
    "cotizar": AgentTool(
        declaration=_COTIZAR_DECLARATION,
        handler=_cotizar,
    ),
    "ajustar_comparar": AgentTool(
        declaration=_AJUSTAR_COMPARAR_DECLARATION,
        handler=_ajustar_comparar,
    ),
    "cerrar_venta": AgentTool(
        declaration=_CERRAR_VENTA_DECLARATION,
        handler=_cerrar_venta,
    ),
}


def tool_declarations() -> list[dict[str, Any]]:
    """Declaraciones Gemini de todas las tools registradas, orden estable."""
    return [tool.declaration for tool in AGENT_TOOLS.values()]


def execute_tool(
    name: str, args: dict[str, Any], ctx: ToolContext
) -> dict[str, Any]:
    """Ejecuta una tool por nombre; nunca propaga excepciones al LLM."""
    tool = AGENT_TOOLS.get(name)
    if tool is None:
        return {
            "error": "tool desconocida",
            "detail": f"No existe una tool registrada con nombre '{name}'.",
        }

    try:
        return tool.handler(args, ctx)
    except Exception as exc:  # noqa: BLE001 - error controlado hacia el LLM
        return {
            "error": "fallo al ejecutar la tool",
            "detail": f"{name}: {exc}",
        }
