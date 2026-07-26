"""Tests for the simulated RUNT integration — TDD RED phase (plan B5, Fase 2).

Covers Fase 2 del plan B5 (`.claude/analysis/plans/
20260725-b5-preguntas-por-categoria-matriz.plan.md`): el módulo nuevo
`app.services.integrations.runt` (`consultar_vehiculo`), la tool nueva
`consultar_vehiculo` en `AGENT_TOOLS` (7 tools en total), los campos nuevos
de vehículo en `ProfileData`, el factor `vehicle_type` ya declarado en
`movilidad-auto` (Fase 1) y la Matriz de Perfilamiento de `movilidad` con
soporte estructurado para marca/línea/año/placa/uso del vehículo.

`app.services.integrations.runt` no existe todavía — todos los tests de este
archivo fallan hoy con `ModuleNotFoundError` en el import de módulo (falla en
la COLECCIÓN, antes de ejecutar ningún test). Una vez exista el módulo
(Fase 2, paso 2) y se completen los campos de `ProfileData`, la tool nueva y
los cambios en `profiling_matrix.py`, estos tests deben pasar en verde.

Contrato asumido para `app.services.integrations.runt` (lo fija este archivo,
lo implementa el paso 2):

- `consultar_vehiculo(placa: str) -> dict`: normaliza la placa (mayúsculas,
  sin guiones/espacios), resuelve contra `PLACAS_DEMO` (dict público,
  `placa normalizada -> vehículo`, al menos 8 entradas, con al menos una
  moto) y, si no está en el catálogo demo, cae a un fallback determinista
  (hash de la placa sobre una lista fija) — misma placa siempre da el mismo
  vehículo, con las mismas claves que un vehículo demo. Placa vacía o sin
  caracteres alfanuméricos devuelve `{"error": ..., "detail": ...}`, nunca
  lanza excepción.
- Cada vehículo resuelto trae las claves: `placa`, `marca`, `linea`,
  `modelo` (int, año), `tipo` (`"auto"` | `"moto"`), `cilindraje`,
  `historial`, `fuente` (`"RUNT simulado"`).
"""

from __future__ import annotations

import pytest

from app.schemas.conversation import ConversationCreate, ProfileData
from app.services.agent_tools import (
    AGENT_TOOLS,
    ToolContext,
    execute_tool,
    tool_declarations,
)
from app.services.conversation import conversation_service
from app.services.integrations.gemini_client import FALLBACK_MESSAGE, GeminiReply
from app.services.integrations.runt import PLACAS_DEMO, consultar_vehiculo
from app.services.profiling_matrix import campos_pendientes
from app.services.quote import QuoteService

import app.services.orchestrator as orchestrator


def _new_session() -> str:
    session = conversation_service.create(ConversationCreate())
    return session.session_id


def _scripted_llm(replies: list[GeminiReply]):
    """Copia local del helper de `test_orchestrator.py`: guion de `generate_reply`."""

    calls: list[dict] = []

    def _generate_reply(contents, *, tools=None, system_instruction=None):
        calls.append(
            {
                "contents": contents,
                "tools": tools,
                "system_instruction": system_instruction,
            }
        )
        assert len(calls) <= len(replies), (
            "LLM script exhausted: more calls than scripted replies"
        )
        return replies[len(calls) - 1]

    _generate_reply.calls = calls
    return _generate_reply


class TestConsultarVehiculoModulo:
    def test_placa_demo_xyz987_devuelve_chevrolet_spark_2020(self) -> None:
        vehiculo = consultar_vehiculo("XYZ987")

        assert vehiculo["placa"] == "XYZ987"
        assert vehiculo["marca"] == "Chevrolet"
        assert vehiculo["linea"] == "Spark"
        assert vehiculo["modelo"] == 2020
        assert vehiculo["tipo"] == "auto"
        assert vehiculo["cilindraje"] == 1200
        assert vehiculo["historial"] == "limpio"
        assert vehiculo["fuente"] == "RUNT simulado"

    def test_normalizacion_placa_minusculas_y_guion_es_equivalente(self) -> None:
        assert consultar_vehiculo("xyz-987") == consultar_vehiculo("XYZ987")

    def test_normalizacion_placa_con_espacios(self) -> None:
        assert consultar_vehiculo("xyz 987") == consultar_vehiculo("XYZ987")

    def test_fallback_determinista_misma_placa_desconocida_mismo_vehiculo(
        self,
    ) -> None:
        primera = consultar_vehiculo("ZZZ999")
        segunda = consultar_vehiculo("ZZZ999")

        assert "error" not in primera
        assert primera == segunda
        assert set(primera.keys()) == {
            "placa",
            "marca",
            "linea",
            "modelo",
            "tipo",
            "cilindraje",
            "historial",
            "fuente",
        }
        assert primera["placa"] == "ZZZ999"

    def test_fallback_determinista_placas_distintas_pueden_diferir(self) -> None:
        vehiculo_a = consultar_vehiculo("AAA111")
        vehiculo_b = consultar_vehiculo("BBB222")

        # No garantizamos que nunca coincidan (podrían caer en el mismo bucket
        # del hash), pero cada una debe seguir siendo determinista consigo misma.
        assert vehiculo_a == consultar_vehiculo("AAA111")
        assert vehiculo_b == consultar_vehiculo("BBB222")

    def test_placa_vacia_devuelve_error_sin_excepcion(self) -> None:
        resultado = consultar_vehiculo("")

        assert isinstance(resultado, dict)
        assert "error" in resultado
        assert "detail" in resultado

    def test_placa_sin_caracteres_alfanumericos_devuelve_error(self) -> None:
        resultado = consultar_vehiculo("---")

        assert isinstance(resultado, dict)
        assert "error" in resultado

    def test_placas_demo_tienen_al_menos_ocho_entradas_e_incluyen_xyz987(
        self,
    ) -> None:
        assert len(PLACAS_DEMO) >= 8
        assert "XYZ987" in PLACAS_DEMO

    def test_al_menos_una_placa_demo_es_moto(self) -> None:
        assert any(v["tipo"] == "moto" for v in PLACAS_DEMO.values())


class TestConsultarVehiculoTool:
    def test_registrada_en_agent_tools(self) -> None:
        assert "consultar_vehiculo" in AGENT_TOOLS

    def test_tool_declarations_tiene_ocho_entradas_e_incluye_consultar_vehiculo(
        self,
    ) -> None:
        # Nota (merge A4+B5): con `enriquecer_perfil` (A4) el total sube a 8.
        declarations = tool_declarations()

        assert len(declarations) == 8
        nombres = [decl["name"] for decl in declarations]
        assert "consultar_vehiculo" in nombres

    def test_con_perfil_existente_actualiza_ctx_profile(self) -> None:
        ctx = ToolContext(session_id="s1")
        ctx.profile = ProfileData(source="declarado", age_range="26-40")

        resultado = execute_tool(
            "consultar_vehiculo", {"placa": "XYZ-987"}, ctx
        )

        assert isinstance(resultado, dict)
        assert "error" not in resultado
        assert resultado["marca"] == "Chevrolet"
        assert resultado["linea"] == "Spark"
        assert resultado["modelo"] == 2020

        assert ctx.profile is not None
        assert ctx.profile.vehicle_brand == "Chevrolet"
        assert ctx.profile.vehicle_year == 2020
        assert ctx.profile.vehicle_type == "auto"
        assert ctx.profile.vehicle_plate == "XYZ987"

    def test_sin_perfil_previo_crea_perfil_declarado_con_vehiculo(self) -> None:
        ctx = ToolContext(session_id="s2")
        assert ctx.profile is None

        resultado = execute_tool(
            "consultar_vehiculo", {"placa": "XYZ-987"}, ctx
        )

        assert "error" not in resultado
        assert ctx.profile is not None
        assert ctx.profile.source == "declarado"
        assert ctx.profile.vehicle_brand == "Chevrolet"
        assert ctx.profile.vehicle_year == 2020
        assert ctx.profile.vehicle_type == "auto"
        assert ctx.profile.vehicle_plate == "XYZ987"

    def test_placa_invalida_devuelve_error_sin_excepcion(self) -> None:
        ctx = ToolContext(session_id="s3")

        resultado = execute_tool("consultar_vehiculo", {"placa": ""}, ctx)

        assert isinstance(resultado, dict)
        assert "error" in resultado


class TestFactorVehiculoActivo:
    def _profile(self, **kwargs) -> ProfileData:
        return ProfileData(source="declarado", age_range="26-40", **kwargs)

    def test_moto_es_065_veces_la_prima_de_auto(self) -> None:
        service = QuoteService()

        cotizacion_auto = service.calculate_quote(
            self._profile(vehicle_type="auto"), product_id="movilidad-auto"
        )
        cotizacion_moto = service.calculate_quote(
            self._profile(vehicle_type="moto"), product_id="movilidad-auto"
        )

        assert cotizacion_moto["annual_premium"] == round(
            0.65 * cotizacion_auto["annual_premium"], 2
        )
        assert cotizacion_moto["monthly_premium"] == round(
            cotizacion_moto["annual_premium"] / 12, 2
        )

    def test_sin_vehicle_type_es_neutro_e_igual_a_auto(self) -> None:
        service = QuoteService()

        cotizacion_auto = service.calculate_quote(
            self._profile(vehicle_type="auto"), product_id="movilidad-auto"
        )
        cotizacion_sin_tipo = service.calculate_quote(
            self._profile(), product_id="movilidad-auto"
        )

        assert cotizacion_sin_tipo["annual_premium"] == cotizacion_auto["annual_premium"]
        assert cotizacion_sin_tipo["monthly_premium"] == cotizacion_auto["monthly_premium"]


class TestMatrizMovilidadConVehiculo:
    def test_perfil_con_vehiculo_resuelto_marca_linea_y_modelo_anio_conocidos(
        self,
    ) -> None:
        profile = ProfileData(
            source="declarado",
            age_range="26-40",
            vehicle_brand="Chevrolet",
            vehicle_year=2020,
        )

        resultado = campos_pendientes("movilidad", profile)

        conocidos_por_campo = {
            item["campo"]: item for item in resultado["conocidos"]
        }
        pendientes_campos = {item["campo"] for item in resultado["pendientes"]}

        assert "marca_linea" in conocidos_por_campo
        assert conocidos_por_campo["marca_linea"]["fuente"] == "RUNT simulado"
        assert "modelo_anio" in conocidos_por_campo
        assert conocidos_por_campo["modelo_anio"]["fuente"] == "RUNT simulado"

        assert "marca_linea" not in pendientes_campos
        assert "modelo_anio" not in pendientes_campos

    def test_perfil_sin_vehiculo_deja_placa_pendiente(self) -> None:
        profile = ProfileData(source="declarado", age_range="26-40")

        resultado = campos_pendientes("movilidad", profile)

        pendientes_campos = {item["campo"] for item in resultado["pendientes"]}
        assert "placa" in pendientes_campos

    def test_placa_declarada_pasa_a_conocidos(self) -> None:
        profile = ProfileData(
            source="declarado", age_range="26-40", vehicle_plate="XYZ987"
        )

        resultado = campos_pendientes("movilidad", profile)

        conocidos_por_campo = {
            item["campo"]: item for item in resultado["conocidos"]
        }
        assert "placa" in conocidos_por_campo


class TestConversacionMovilidadGuionada:
    """Guion e2e (patrón `_scripted_llm` de `test_orchestrator.py`): la placa
    se resuelve con `consultar_vehiculo` ANTES de cotizar, y el bot cita el
    vehículo resuelto en su respuesta intermedia.
    """

    def test_consultar_vehiculo_se_ejecuta_antes_que_cotizar(
        self, monkeypatch
    ) -> None:
        sid = _new_session()

        orden_ejecutado: list[str] = []
        original_execute_tool = orchestrator.execute_tool

        def _execute_tool_spy(name, args, ctx):
            orden_ejecutado.append(name)
            return original_execute_tool(name, args, ctx)

        monkeypatch.setattr(orchestrator, "execute_tool", _execute_tool_spy)

        # Turno 1: el cliente da la placa, el bot la consulta y confirma el
        # vehículo encontrado en el RUNT simulado.
        llm_turno_1 = _scripted_llm(
            [
                GeminiReply(
                    kind="tool_call",
                    tool_name="consultar_vehiculo",
                    tool_args={"placa": "XYZ-987"},
                ),
                GeminiReply(
                    kind="text",
                    text=(
                        "Encontré tu vehículo: Chevrolet Spark 2020. "
                        "¿Seguimos con la cotización?"
                    ),
                ),
            ]
        )
        monkeypatch.setattr(orchestrator, "generate_reply", llm_turno_1)

        resultado_1 = orchestrator.respond(sid, "mi placa es XYZ-987")

        assert resultado_1 is not None
        mensaje_intermedio = resultado_1.messages[-1]
        assert mensaje_intermedio.role == "assistant"
        assert "Chevrolet Spark" in mensaje_intermedio.content

        # Turno 2: el cliente confirma, el bot cotiza.
        llm_turno_2 = _scripted_llm(
            [
                GeminiReply(kind="tool_call", tool_name="cotizar", tool_args={}),
                GeminiReply(kind="text", text="Tu cotización ya está lista."),
            ]
        )
        monkeypatch.setattr(orchestrator, "generate_reply", llm_turno_2)

        resultado_2 = orchestrator.respond(sid, "sí, cotiza")

        assert resultado_2 is not None
        assert resultado_2.quote is not None

        assert "consultar_vehiculo" in orden_ejecutado
        assert "cotizar" in orden_ejecutado
        assert orden_ejecutado.index("consultar_vehiculo") < orden_ejecutado.index(
            "cotizar"
        )
