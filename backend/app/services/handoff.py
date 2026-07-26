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
    "accidentes-personales": "Seguros Sura",
    "vida-basico": "Seguros Bolívar",
    "movilidad-auto": "Mapfre",
    "credito-vida-deudor": "Aseguradora Solidaria",
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

    # Estilos inline y layout de tablas: es lo único que renderizan de forma
    # consistente Gmail, Outlook y clientes móviles (los <style> se descartan).
    body_font = "Helvetica Neue, Helvetica, Arial, sans-serif"
    display_font = "Georgia, 'Times New Roman', serif"

    coverage_items = "".join(
        f"""
        <tr>
          <td width="28" valign="top" style="padding:6px 0;color:#00754a;font-family:{body_font};font-size:15px;font-weight:bold;">&#10003;</td>
          <td valign="top" style="padding:6px 0;color:#1f2a24;font-family:{body_font};font-size:15px;line-height:22px;">{coverage}</td>
        </tr>"""
        for coverage in application.quote.coverage_details
    )
    reason_items = "".join(
        f"""
        <tr>
          <td style="padding:0 0 12px 0;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f5;border-left:4px solid #00754a;border-radius:0 8px 8px 0;">
              <tr>
                <td style="padding:12px 16px;">
                  <p style="margin:0 0 2px 0;color:#005c3a;font-family:{body_font};font-size:14px;font-weight:bold;">{reason.get('label', '')}</p>
                  <p style="margin:0;color:#6b7570;font-family:{body_font};font-size:13px;line-height:19px;">{reason.get('evidence', '')}</p>
                </td>
              </tr>
            </table>
          </td>
        </tr>"""
        for reason in application.recommendation.reasons
    )

    html = f"""
    <html>
      <body style="margin:0;padding:0;background-color:#eef1ef;">
        <!-- Preheader oculto: texto de preview en la bandeja de entrada -->
        <div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">
          Tu solicitud de {product_name} qued&oacute; registrada. Solo falta un paso: conf&iacute;rmala con {insurer_name}.
        </div>

        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#eef1ef;">
          <tr>
            <td align="center" style="padding:32px 16px;">
              <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">

                <!-- Encabezado de marca -->
                <tr>
                  <td style="background-color:#005c3a;border-radius:12px 12px 0 0;padding:22px 32px;">
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                      <tr>
                        <td style="color:#ffffff;font-family:{display_font};font-size:20px;letter-spacing:0.5px;">Tu Asesor de Seguros</td>
                        <td align="right" style="color:#9fd6bd;font-family:{body_font};font-size:11px;text-transform:uppercase;letter-spacing:1.5px;">Comprobante</td>
                      </tr>
                    </table>
                  </td>
                </tr>

                <!-- Héroe: qué pasó y qué producto -->
                <tr>
                  <td style="background-color:#00754a;padding:36px 32px 32px 32px;">
                    <p style="margin:0 0 8px 0;color:#d9f2e6;font-family:{body_font};font-size:14px;">&iexcl;Buenas noticias! Tu solicitud qued&oacute; registrada &#127881;</p>
                    <h1 style="margin:0;color:#ffffff;font-family:{display_font};font-size:32px;line-height:38px;font-weight:normal;">{product_name}</h1>
                  </td>
                </tr>

                <!-- Tarjeta de precio -->
                <tr>
                  <td style="background-color:#ffffff;padding:32px 32px 8px 32px;">
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#e6f4ee;border-radius:12px;">
                      <tr>
                        <td align="center" style="padding:24px 16px 20px 16px;">
                          <p style="margin:0 0 4px 0;color:#005c3a;font-family:{body_font};font-size:12px;text-transform:uppercase;letter-spacing:2px;">Tu prima mensual</p>
                          <p style="margin:0;color:#005c3a;font-family:{display_font};font-size:44px;line-height:48px;">${monthly}<span style="font-size:18px;"> {currency}</span></p>
                          <p style="margin:8px 0 0 0;color:#6b7570;font-family:{body_font};font-size:13px;">Prima anual: ${annual} {currency}</p>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>

                <!-- Llamado a la acci&oacute;n -->
                <tr>
                  <td align="center" style="background-color:#ffffff;padding:24px 32px 12px 32px;">
                    <p style="margin:0 0 16px 0;color:#1f2a24;font-family:{body_font};font-size:16px;line-height:24px;">
                      Solo falta <strong>un paso</strong>: confirma tu solicitud con <strong>{insurer_name}</strong> y tu cobertura queda en marcha.
                    </p>
                    <table role="presentation" cellpadding="0" cellspacing="0">
                      <tr>
                        <td align="center" style="background-color:#00754a;border-radius:999px;">
                          <a href="{handoff_url}" style="display:inline-block;padding:16px 44px;color:#ffffff;font-family:{body_font};font-size:17px;font-weight:bold;text-decoration:none;border-radius:999px;">
                            Confirmar y finalizar con {insurer_name} &rarr;
                          </a>
                        </td>
                      </tr>
                    </table>
                    <p style="margin:14px 0 0 0;color:#6b7570;font-family:{body_font};font-size:12px;">Toma menos de 2 minutos.</p>
                  </td>
                </tr>

                <!-- Coberturas -->
                <tr>
                  <td style="background-color:#ffffff;padding:24px 32px 8px 32px;">
                    <h2 style="margin:0 0 8px 0;color:#1f2a24;font-family:{display_font};font-size:20px;font-weight:normal;border-bottom:1px solid #e0e5e2;padding-bottom:8px;">Lo que cubre tu seguro</h2>
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{coverage_items}
                    </table>
                  </td>
                </tr>

                <!-- Razones de la recomendaci&oacute;n -->
                <tr>
                  <td style="background-color:#ffffff;padding:24px 32px 8px 32px;">
                    <h2 style="margin:0 0 14px 0;color:#1f2a24;font-family:{display_font};font-size:20px;font-weight:normal;border-bottom:1px solid #e0e5e2;padding-bottom:8px;">Por qu&eacute; es para ti</h2>
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{reason_items}
                    </table>
                  </td>
                </tr>

                <!-- Detalle del consentimiento -->
                <tr>
                  <td style="background-color:#ffffff;border-radius:0 0 12px 12px;padding:16px 32px 28px 32px;">
                    <p style="margin:0;color:#6b7570;font-family:{body_font};font-size:12px;line-height:18px;">
                      Consentimiento registrado: {application.consent_timestamp}<br>
                      Si el bot&oacute;n no funciona, copia y pega este enlace en tu navegador:<br>
                      <a href="{handoff_url}" style="color:#00754a;word-break:break-all;">{handoff_url}</a>
                    </p>
                  </td>
                </tr>

                <!-- Pie: etiqueta de simulaci&oacute;n -->
                <tr>
                  <td align="center" style="padding:20px 32px;">
                    <p style="margin:0;color:#6b7570;font-family:{body_font};font-size:12px;line-height:18px;">
                      <em>Simulaci&oacute;n — entorno de demostraci&oacute;n. Este correo no representa una p&oacute;liza real.</em>
                    </p>
                  </td>
                </tr>

              </table>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """

    return subject, html
