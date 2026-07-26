"""Servicio del panel de clientes: búsqueda y ficha de detalle (plan G4, Fase 3).

Agrega, sin persistencia propia, los datos de conversaciones, solicitudes y
perfil enriquecido por **cliente** — agrupados por SERIE cuando la sesión (o
alguna de sus filas de `perfil_enriquecido`) la trae, o por `session_id` para
prospectos anónimos que nunca se identificaron.

Regla de capas del backend/CLAUDE.md: este service compone otros SERVICES
(`ConversationService`, `ConsentService`, `EnrichmentService`,
`AffiliateService`), nunca toca un repositorio ajeno directamente.

Escaneo completo en memoria por request (listas completas de cada service):
aceptable a escala hackathon, no es un patrón de producción — mismo criterio
ya documentado en los métodos `list_all()` de la Fase 2.
"""

from __future__ import annotations

import dataclasses

from app.models.enriched_field import EnrichedFieldRecord
from app.models.affiliate import AffiliateProfile
from app.schemas.conversation import ConsentedApplication, ConversationState
from app.services.affiliate import AffiliateService
from app.services.consent import ConsentService
from app.services.conversation import ConversationService
from app.services.enrichment import EnrichmentService

# Campos de `AffiliateProfile` cuyo valor real proviene de una columna
# sintética (`sint_*`) de `afiliados`, no del dataset real de Colsubsidio: se
# muestran en la ficha con el nombre de la columna de origen y
# `origen="sintetico"` (ver `AffiliateRepository._record_to_profile`).
_SYNTHETIC_FIELDS = {
    "property_type": "sint_tipo_vivienda",
    "has_children": "sint_tiene_hijos",
    "has_vehicle": "sint_tiene_vehiculo",
    "has_credit": "sint_tiene_credito",
}
# Campo redundante con `serie`/`cliente_id`: no aporta como fila de perfil.
_AFFILIATE_SKIP_FIELDS = {"document_number"}


def _to_str(valor: object) -> str:
    """Serializa un valor de perfil a texto (bool -> "true"/"false")."""
    if isinstance(valor, bool):
        return "true" if valor else "false"
    return str(valor)


@dataclasses.dataclass
class _ClienteAgg:
    """Acumulador interno por cliente mientras se agrupan sesiones/solicitudes/EAV."""

    cliente_id: str
    serie: str | None = None
    sesiones: list[dict] = dataclasses.field(default_factory=list)
    solicitudes: list[ConsentedApplication] = dataclasses.field(default_factory=list)
    filas_enriquecidas: list[EnrichedFieldRecord] = dataclasses.field(default_factory=list)


class PanelClientesService:
    """Vista agregada de clientes para el panel: búsqueda y ficha de detalle."""

    def __init__(self) -> None:
        self._conversations = ConversationService()
        self._consent = ConsentService()
        self._enrichment = EnrichmentService()
        self._affiliates = AffiliateService()

    # -- listado --------------------------------------------------------------

    def list_clientes(self, q: str | None = None) -> dict:
        """Lista clientes, filtrados por `q` (serie exacta / email / nombre)."""
        clientes = self._agrupar().values()
        resumenes = [self._resumen(cliente) for cliente in clientes]

        texto = (q or "").strip()
        if texto:
            texto_lower = texto.lower()
            resumenes = [
                resumen
                for resumen in resumenes
                if resumen["serie"] == texto
                or (resumen["email"] and texto_lower in resumen["email"].lower())
                or (resumen["nombre"] and texto_lower in resumen["nombre"].lower())
            ]

        resumenes.sort(key=lambda r: r["ultima_actividad"] or "", reverse=True)
        return {"total": len(resumenes), "clientes": resumenes}

    # -- ficha ------------------------------------------------------------------

    def ficha(self, cliente_id: str) -> dict:
        """Ficha de detalle de un cliente (perfil fusionado + funnel)."""
        cliente = self._agrupar().get(cliente_id)
        if cliente is None:
            raise ValueError("Cliente not found")

        afiliado_profile = (
            self._affiliates.lookup(cliente.serie) if cliente.serie else None
        )
        afiliado = self._es_afiliado(cliente, afiliado_profile)
        fuente_perfil = "base" if afiliado else "declarado"
        perfil = self._perfil(cliente, afiliado_profile, afiliado)

        ofertas: list[dict] = []
        cotizaciones: list[dict] = []
        conversaciones: list[dict] = []

        for item in cliente.sesiones:
            session = item["session"]
            conversaciones.append(
                {
                    "session_id": session.session_id,
                    "canal": item["canal"],
                    "estado": session.state.value,
                    "mensajes": len(session.messages),
                    "inicio": item["created_at"].isoformat(),
                    "ultima_actividad": item["updated_at"].isoformat(),
                }
            )

            if session.recommendation is not None:
                proactivo = bool(session.messages) and session.messages[0].role == "assistant"
                fecha_oferta = (
                    session.messages[0].timestamp
                    if session.messages
                    else item["created_at"].isoformat()
                )
                ofertas.append(
                    {
                        "session_id": session.session_id,
                        "product_id": session.recommendation.product_id,
                        "product_name": session.recommendation.product_name,
                        "tipo": "proactivo" if proactivo else "recomendacion",
                        "fecha": fecha_oferta,
                    }
                )

            if session.quote is not None:
                cotizaciones.append(
                    {
                        "session_id": session.session_id,
                        "product_id": (
                            session.recommendation.product_id
                            if session.recommendation
                            else None
                        ),
                        "product_name": (
                            session.recommendation.product_name
                            if session.recommendation
                            else None
                        ),
                        "monthly_premium": session.quote.monthly_premium,
                        "fecha": item["updated_at"].isoformat(),
                    }
                )

        solicitudes = [
            {
                "session_id": application.session_id,
                "product_id": application.product_id,
                "estado": application.state.value,
                "comprado": application.state == ConversationState.FINALIZED_DEMO,
                "email": application.email,
                "fecha": application.consent_timestamp,
            }
            for application in cliente.solicitudes
        ]

        return {
            "cliente_id": cliente.cliente_id,
            "serie": cliente.serie,
            "afiliado": afiliado,
            "fuente_perfil": fuente_perfil,
            "perfil": perfil,
            "ofertas": ofertas,
            "cotizaciones": cotizaciones,
            "solicitudes": solicitudes,
            "conversaciones": conversaciones,
        }

    # -- agrupación por cliente ---------------------------------------------

    def _agrupar(self) -> dict[str, _ClienteAgg]:
        """Agrupa sesiones, solicitudes y filas EAV por `cliente_id`.

        `cliente_id` = SERIE de la sesión (Fase 1) o, para sesiones viejas sin
        el campo, la SERIE que traiga alguna fila de `perfil_enriquecido` de
        esa sesión (asociación histórica); si ninguna vía resuelve serie, el
        cliente es un prospecto y `cliente_id = session_id`. Las solicitudes
        se asocian por su propio `session_id`.
        """
        sesiones = self._conversations.list_sessions()
        solicitudes = self._consent.list_applications()
        filas = self._enrichment.all_fields()

        serie_por_session: dict[str, str] = {
            fila.session_id: fila.serie for fila in filas if fila.serie
        }

        clientes: dict[str, _ClienteAgg] = {}
        session_a_cliente: dict[str, str] = {}

        for item in sesiones:
            session = item["session"]
            serie = session.serie or serie_por_session.get(session.session_id)
            cliente_id = serie or session.session_id
            cliente = clientes.setdefault(cliente_id, _ClienteAgg(cliente_id=cliente_id))
            if serie:
                cliente.serie = serie
            cliente.sesiones.append(item)
            session_a_cliente[session.session_id] = cliente_id

        for application in solicitudes:
            cliente_id = session_a_cliente.get(application.session_id, application.session_id)
            cliente = clientes.setdefault(cliente_id, _ClienteAgg(cliente_id=cliente_id))
            cliente.solicitudes.append(application)

        for fila in filas:
            cliente_id = session_a_cliente.get(fila.session_id) or fila.serie or fila.session_id
            cliente = clientes.setdefault(cliente_id, _ClienteAgg(cliente_id=cliente_id))
            cliente.filas_enriquecidas.append(fila)

        return clientes

    # -- helpers de resumen/ficha ---------------------------------------------

    def _es_afiliado(
        self, cliente: _ClienteAgg, afiliado_profile: AffiliateProfile | None
    ) -> bool:
        """Afiliado = tiene serie y (lookup real o marca `source == "base"`)."""
        if not cliente.serie:
            return False
        if afiliado_profile is not None:
            return True
        return any(
            item["session"].profile is not None
            and item["session"].profile.source == "base"
            for item in cliente.sesiones
        )

    def _ultimo_valor(self, filas: list[EnrichedFieldRecord], campo: str) -> str | None:
        """Última escritura (mayor `id`, filas ya vienen en orden ascendente)."""
        valor: str | None = None
        for fila in filas:
            if fila.campo == campo:
                valor = fila.valor
        return valor

    def _resumen(self, cliente: _ClienteAgg) -> dict:
        afiliado_profile = (
            self._affiliates.lookup(cliente.serie) if cliente.serie else None
        )
        afiliado = self._es_afiliado(cliente, afiliado_profile)
        nombre = self._ultimo_valor(cliente.filas_enriquecidas, "nombre")

        email = None
        for application in cliente.solicitudes:
            if application.email:
                email = application.email
                break

        ultimo_estado = None
        ultima_actividad = None
        if cliente.sesiones:
            mas_reciente = max(cliente.sesiones, key=lambda item: item["updated_at"])
            ultimo_estado = mas_reciente["session"].state.value
            ultima_actividad = mas_reciente["updated_at"].isoformat()

        return {
            "cliente_id": cliente.cliente_id,
            "serie": cliente.serie,
            "afiliado": afiliado,
            "nombre": nombre,
            "email": email,
            "conversaciones": len(cliente.sesiones),
            "solicitudes": len(cliente.solicitudes),
            "ultimo_estado": ultimo_estado,
            "ultima_actividad": ultima_actividad,
        }

    def _primer_perfil_sesion(self, cliente: _ClienteAgg, source: str | None = None):
        """Primer `ProfileData` no-nulo entre las sesiones del cliente."""
        for item in cliente.sesiones:
            profile = item["session"].profile
            if profile is None:
                continue
            if source is not None and profile.source != source:
                continue
            return profile
        return None

    def _perfil(
        self,
        cliente: _ClienteAgg,
        afiliado_profile: AffiliateProfile | None,
        afiliado: bool,
    ) -> list[dict]:
        """Perfil fusionado: base/sintético/declarado + conversación (pisa)."""
        perfil: dict[str, dict] = {}

        if afiliado and afiliado_profile is not None:
            for campo_dataclass in dataclasses.fields(afiliado_profile):
                nombre_campo = campo_dataclass.name
                if nombre_campo in _AFFILIATE_SKIP_FIELDS:
                    continue
                valor = getattr(afiliado_profile, nombre_campo)
                if valor is None:
                    continue
                if nombre_campo in _SYNTHETIC_FIELDS:
                    campo = _SYNTHETIC_FIELDS[nombre_campo]
                    origen = "sintetico"
                else:
                    campo = nombre_campo
                    origen = "base"
                perfil[campo] = {"campo": campo, "valor": _to_str(valor), "origen": origen}
        elif afiliado:
            # Afiliado sin registro en `afiliados` (fuente = marca de la sesión):
            # usar el perfil declarado que la sesión resolvió como "base".
            declarado = self._primer_perfil_sesion(cliente, source="base")
            if declarado is not None:
                for nombre_campo, valor in declarado.model_dump().items():
                    if valor is None or nombre_campo == "source":
                        continue
                    perfil[nombre_campo] = {
                        "campo": nombre_campo,
                        "valor": _to_str(valor),
                        "origen": "base",
                    }
        else:
            declarado = self._primer_perfil_sesion(cliente)
            if declarado is not None:
                for nombre_campo, valor in declarado.model_dump().items():
                    if valor is None or nombre_campo == "source":
                        continue
                    perfil[nombre_campo] = {
                        "campo": nombre_campo,
                        "valor": _to_str(valor),
                        "origen": "declarado",
                    }

        # Campos del perfil enriquecido en conversación: última escritura gana
        # y pisa cualquier valor de base/sintético/declarado del mismo nombre.
        ultimos: dict[str, str] = {}
        for fila in cliente.filas_enriquecidas:
            ultimos[fila.campo] = fila.valor
        for campo, valor in ultimos.items():
            perfil[campo] = {"campo": campo, "valor": valor, "origen": "conversacion"}

        return list(perfil.values())
