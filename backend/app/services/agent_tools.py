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

from dataclasses import dataclass
from typing import Any, Callable

from app.schemas.conversation import ProfileData
from app.services.affiliate import AffiliateService
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
        "perfil con los datos que el cliente haya declarado en la "
        "conversación sobre su hogar (tipo de propiedad, zona, estrato, rango "
        "de edad, si tiene familia). Devuelve si es afiliado, la fuente del "
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
    )
    has_declared_data = any(
        value is not None
        for value in (
            declared.property_type,
            declared.zone,
            declared.stratum,
            declared.age_range,
            declared.has_family,
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
        "Calcula la prima del seguro de hogar con el motor determinista de "
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

    adjustments = args.get("adjustments") or []
    result = QuoteService().calculate_quote(ctx.profile, adjustments)
    ctx.quote = result
    return {**result, "product_id": "hogar-estandar"}


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
