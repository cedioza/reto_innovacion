"""Servicio de handoff: aseguradora simulada, token y comprobante por correo.

Construye el token opaco que identifica el handoff y el contenido (asunto +
HTML inline, sin plantillas) del correo de comprobante que se envía al
cliente al capturar su consentimiento. No envía nada por sí mismo — eso lo
hace `app.services.integrations.resend_client.send_email` con el resultado
de `build_handoff_email`.
"""

import secrets

from app.schemas.conversation import ConsentedApplication

INSURER_BY_PRODUCT: dict[str, str] = {
    "hogar-estandar": "Seguros Bolívar",
}

_INSURER_FALLBACK = "la aseguradora aliada"


def insurer_for(product_id: str) -> str:
    """Devuelve el nombre de la aseguradora simulada asociada al producto.

    Si el producto no tiene aseguradora mapeada, cae en un nombre genérico
    ("la aseguradora aliada") en vez de fallar — el handoff nunca se bloquea
    por un producto sin mapeo explícito.
    """
    return INSURER_BY_PRODUCT.get(product_id, _INSURER_FALLBACK)


def new_token() -> str:
    """Genera un token opaco, único y URL-safe para identificar el handoff."""
    return secrets.token_urlsafe(32)


def _formato_miles(monto: float) -> str:
    """Formatea un monto con separador de miles "." (estilo colombiano).

    Réplica local (sin importar de `orchestrator`) para no acoplar este
    servicio al orquestador conversacional.
    """
    return f"{round(monto):,}".replace(",", ".")


def build_handoff_email(
    application: ConsentedApplication, token: str
) -> tuple[str, str]:
    """Arma el asunto y el HTML del correo de comprobante de la solicitud.

    El correo cita únicamente cifras y razones que ya vienen del motor
    (`application.quote` / `application.recommendation`) — nunca inventa
    datos. Incluye el link de handoff hacia la aseguradora simulada y la
    etiqueta de simulación, visible en todo momento.
    """
    from app.core.config import settings

    product_name = application.recommendation.product_name
    insurer_name = insurer_for(application.product_id)
    handoff_url = f"{settings.frontend_url}/aseguradora/{token}"

    subject = f"Comprobante de tu solicitud — {product_name}"

    monthly = _formato_miles(application.quote.monthly_premium)
    annual = (
        _formato_miles(application.quote.annual_premium)
        if application.quote.annual_premium is not None
        else "N/A"
    )
    currency = application.quote.currency

    coverage_items = "".join(
        f"<li>{coverage}</li>" for coverage in application.quote.coverage_details
    )
    reason_items = "".join(
        f"<li><strong>{reason.get('label', '')}</strong>: "
        f"{reason.get('evidence', '')}</li>"
        for reason in application.recommendation.reasons
    )

    html = f"""
    <html>
      <body>
        <h1>Comprobante de tu solicitud</h1>
        <p>Producto: <strong>{product_name}</strong></p>
        <p>Prima mensual: ${monthly} {currency}</p>
        <p>Prima anual: ${annual} {currency}</p>
        <h2>Coberturas incluidas</h2>
        <ul>{coverage_items}</ul>
        <h2>Por qué te recomendamos este producto</h2>
        <ul>{reason_items}</ul>
        <p>Consentimiento registrado: {application.consent_timestamp}</p>
        <p>
          <a href="{handoff_url}">
            Finalizar con {insurer_name}
          </a>
        </p>
        <p><em>(simulación — entorno de demostración)</em></p>
      </body>
    </html>
    """

    return subject, html
