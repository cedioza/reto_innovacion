"""Tests for the agent tools contract — TDD RED phase.

Covers Fase 1 of the A2 plan (`.claude/analysis/plans/
20260724-a2-contrato-herramientas-agente.plan.md`): the registry scaffolding
(`ToolContext`, `AgentTool`, `AGENT_TOOLS`, `tool_declarations()`,
`execute_tool()`) and the first tool, `perfilar_cliente`, built on top of the
real `AffiliateService`.

`app.services.agent_tools` does not exist yet — every test here is expected
to fail with a ModuleNotFoundError/ImportError until Fase 1 implements it.
"""

import json
from pathlib import Path
import tempfile

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app.core.config import settings
from app.models.affiliate_record import AffiliateRecord
from app.repositories import db as db_module
from app.repositories.db import init_db
from app.schemas.conversation import ProfileData
from app.services.catalog import CatalogService
from app.services.enrichment import EnrichmentService
from app.services.integrations import resend_client
from app.services.propensity import PropensityService
from app.services.quote import QuoteService

from app.services.agent_tools import (
    AGENT_TOOLS,
    AgentTool,
    ToolContext,
    execute_tool,
    tool_declarations,
)

FIXTURE_CSV = """SERIE;GENERO;RANGO_EDAD;RANGO_SALARIO;SEGMENTO_HOGAR;SEGMENTO_POBLACION;CIUDAD;SEÑAL_CONSUMO_1;SEÑAL_CONSUMO_2;SEÑAL_CONSUMO_3;SEÑAL_CONSUMO_4;SEÑAL_CONSUMO_5
A001;M;26-40;2-4M;3;TRABAJADOR;Bogotá;1;0;1;0;1
A002;F;41-55;1-2M;2;HOGAR;Medellín;0;1;0;1;0
A003;M;56-65;4M+;4;JUBILADO;Cali;0;0;0;0;0
"""


class TestToolDeclarations:
    def test_returns_list_of_valid_json_schema_declarations(self) -> None:
        declarations = tool_declarations()
        assert isinstance(declarations, list)
        assert len(declarations) >= 1
        for decl in declarations:
            assert "name" in decl
            assert "description" in decl
            assert "parameters" in decl
            assert isinstance(decl["parameters"], dict)
            assert decl["parameters"].get("type") == "object"

    def test_names_are_unique(self) -> None:
        names = [decl["name"] for decl in tool_declarations()]
        assert len(names) == len(set(names))

    def test_includes_perfilar_cliente_in_phase_1(self) -> None:
        names = [decl["name"] for decl in tool_declarations()]
        assert "perfilar_cliente" in names

    def test_agent_tools_registry_has_perfilar_cliente(self) -> None:
        assert "perfilar_cliente" in AGENT_TOOLS
        assert isinstance(AGENT_TOOLS["perfilar_cliente"], AgentTool)
        assert AGENT_TOOLS["perfilar_cliente"].declaration["name"] == (
            "perfilar_cliente"
        )


class TestPerfilarClienteAffiliateFound:
    """Camino 1 de la Matriz: documento existe en la base -> perfil real."""

    def setup_method(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        )
        self.tmp.write(FIXTURE_CSV)
        self.tmp.close()

    def teardown_method(self) -> None:
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_existing_document_resolves_from_base(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "affiliate_csv_path", self.tmp.name)
        ctx = ToolContext(session_id="s1")

        result = execute_tool(
            "perfilar_cliente", {"document_number": "A001"}, ctx
        )

        assert result["afiliado"] is True
        assert result["fuente"] == "base"
        assert result["profile"]["age_range"] == "26-40"
        assert result["profile"]["stratum"] == 3

        assert isinstance(ctx.profile, ProfileData)
        assert ctx.profile.age_range == "26-40"
        assert ctx.profile.stratum == 3

    def test_result_is_json_safe(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "affiliate_csv_path", self.tmp.name)
        ctx = ToolContext()
        result = execute_tool(
            "perfilar_cliente", {"document_number": "A001"}, ctx
        )
        json.dumps(result)  # must not raise


class TestPerfilarClienteDeclaredFallback:
    """Camino 2 de la Matriz: documento inexistente + datos declarados."""

    def setup_method(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        )
        self.tmp.write(FIXTURE_CSV)
        self.tmp.close()

    def teardown_method(self) -> None:
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_unknown_document_with_declared_data_has_no_exception(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "affiliate_csv_path", self.tmp.name)
        ctx = ToolContext()

        result = execute_tool(
            "perfilar_cliente",
            {
                "document_number": "ZZ999",
                "property_type": "house",
                "zone": "urban",
                "stratum": 4,
                "age_range": "26-40",
                "has_family": True,
            },
            ctx,
        )

        assert result["afiliado"] is False
        assert result["fuente"] == "declarado"
        assert result["profile"]["property_type"] == "house"
        assert result["profile"]["stratum"] == 4

        assert isinstance(ctx.profile, ProfileData)
        assert ctx.profile.property_type == "house"
        assert ctx.profile.stratum == 4
        assert ctx.profile.has_family is True

    def test_result_is_json_safe(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "affiliate_csv_path", self.tmp.name)
        ctx = ToolContext()
        result = execute_tool(
            "perfilar_cliente",
            {"document_number": "ZZ999", "stratum": 4, "age_range": "26-40"},
            ctx,
        )
        json.dumps(result)


class TestPerfilarClienteMinimalDefault:
    """Camino 3 de la Matriz: sin documento y sin declarados -> perfil mínimo."""

    def test_no_document_no_declared_uses_minimal_default(self) -> None:
        ctx = ToolContext()

        result = execute_tool("perfilar_cliente", {}, ctx)

        assert result["afiliado"] is False
        assert "profile" in result
        assert isinstance(ctx.profile, ProfileData)

    def test_result_is_json_safe(self) -> None:
        ctx = ToolContext()
        result = execute_tool("perfilar_cliente", {}, ctx)
        json.dumps(result)


class TestPerfilarClienteSenalesDeclaradas:
    """Señales adicionales (has_children/has_vehicle/has_credit) declaradas
    por el usuario en la conversación, sin depender de la base de afiliados.
    """

    def test_declaracion_incluye_senales_nuevas(self) -> None:
        declarations = tool_declarations()
        perfilar = next(
            decl for decl in declarations if decl["name"] == "perfilar_cliente"
        )
        properties = perfilar["parameters"]["properties"]

        for campo in ("has_children", "has_vehicle", "has_credit"):
            assert campo in properties
            assert properties[campo]["type"] == "boolean"

    def test_captura_vehiculo_declarado(self) -> None:
        ctx = ToolContext()

        result = execute_tool(
            "perfilar_cliente", {"has_vehicle": True}, ctx
        )

        assert ctx.profile.has_vehicle is True
        assert result["profile"]["has_vehicle"] is True
        assert result["fuente"] == "declarado"

    def test_solo_senal_nueva_cuenta_como_dato_declarado(self) -> None:
        ctx = ToolContext()

        result = execute_tool(
            "perfilar_cliente", {"has_credit": True}, ctx
        )

        assert ctx.profile.has_credit is True
        assert result["profile"]["has_credit"] is True

    def test_senales_ausentes_quedan_none(self) -> None:
        ctx = ToolContext()

        execute_tool(
            "perfilar_cliente", {"property_type": "house"}, ctx
        )

        assert ctx.profile.has_children is None
        assert ctx.profile.has_vehicle is None
        assert ctx.profile.has_credit is None

    def test_resultado_json_safe_con_senales(self) -> None:
        ctx = ToolContext()

        result = execute_tool(
            "perfilar_cliente",
            {"has_children": True, "has_vehicle": True, "has_credit": True},
            ctx,
        )

        json.dumps(result)

    def test_captura_hijos_declarados(self) -> None:
        ctx = ToolContext()

        execute_tool(
            "perfilar_cliente",
            {"has_children": True, "has_family": True},
            ctx,
        )

        assert ctx.profile.has_children is True
        assert ctx.profile.has_family is True


class TestExecuteToolUnknownName:
    def test_unknown_tool_returns_error_dict_without_raising(self) -> None:
        ctx = ToolContext()

        result = execute_tool("tool_inexistente", {}, ctx)

        assert isinstance(result, dict)
        assert "error" in result


# --- Fase 2: recomendar_seguro + cotizar ---

FAVORABLE_PROFILE = ProfileData(
    age_range="26-40", stratum=3, property_type="house", zone="urban"
)


class TestToolDeclarationsPhase2:
    def test_includes_recomendar_seguro_and_cotizar(self) -> None:
        declarations = tool_declarations()
        names = [decl["name"] for decl in declarations]

        assert "recomendar_seguro" in names
        assert "cotizar" in names

    def test_has_three_unique_declarations_with_required_keys(self) -> None:
        declarations = tool_declarations()
        names = [decl["name"] for decl in declarations]

        assert len(declarations) >= 3
        assert len(names) == len(set(names))
        for decl in declarations:
            assert "name" in decl
            assert "description" in decl
            assert "parameters" in decl


class TestRecomendarSeguro:
    def test_favorable_profile_matches_propensity_engine(self) -> None:
        ctx = ToolContext(session_id="s1")
        ctx.profile = FAVORABLE_PROFILE.model_copy()

        result = execute_tool("recomendar_seguro", {}, ctx)

        expected = PropensityService().evaluate(FAVORABLE_PROFILE)

        assert result["recommended"] is True
        assert result["recommended"] == expected["recommended"]
        assert result["product_id"] == expected["product_id"]
        assert result["score"] == expected["score"]
        assert result["reasons"] == expected["reasons"]
        for reason in result["reasons"]:
            assert set(reason.keys()) >= {"code", "label", "evidence"}

        assert ctx.recommendation is not None

    def test_result_is_json_safe(self) -> None:
        ctx = ToolContext()
        ctx.profile = FAVORABLE_PROFILE.model_copy()

        result = execute_tool("recomendar_seguro", {}, ctx)

        json.dumps(result)

    def test_without_profile_returns_controlled_error(self) -> None:
        ctx = ToolContext()
        assert ctx.profile is None

        result = execute_tool("recomendar_seguro", {}, ctx)

        assert isinstance(result, dict)
        assert "error" in result
        assert ctx.recommendation is None


class TestCotizar:
    def test_without_adjustments_matches_quote_engine_exactly(self) -> None:
        ctx = ToolContext(session_id="s1")
        ctx.profile = FAVORABLE_PROFILE.model_copy()

        result = execute_tool("cotizar", {}, ctx)

        expected = QuoteService().calculate_quote(FAVORABLE_PROFILE)

        assert result["monthly_premium"] == expected["monthly_premium"]
        assert result["annual_premium"] == expected["annual_premium"]

        assert ctx.quote is not None

    def test_result_is_json_safe(self) -> None:
        ctx = ToolContext()
        ctx.profile = FAVORABLE_PROFILE.model_copy()

        result = execute_tool("cotizar", {}, ctx)

        json.dumps(result)

    def test_with_valid_adjustment_matches_quote_engine(self) -> None:
        product = CatalogService().get_product("hogar-estandar")
        assert product is not None
        assert len(product.adjustments) >= 1
        adjustment_code = product.adjustments[0].code

        ctx = ToolContext(session_id="s1")
        ctx.profile = FAVORABLE_PROFILE.model_copy()

        result = execute_tool(
            "cotizar", {"adjustments": [adjustment_code]}, ctx
        )

        expected = QuoteService().calculate_quote(
            FAVORABLE_PROFILE, [adjustment_code]
        )

        assert result["annual_premium"] == expected["annual_premium"]
        assert result["monthly_premium"] == expected["monthly_premium"]

        result_adjustment_codes = [
            a.get("code") for a in result.get("adjustment_details", [])
        ] or [a.get("code") for a in result.get("adjustments", [])]
        assert adjustment_code in result_adjustment_codes

        base_ctx = ToolContext(session_id="s2")
        base_ctx.profile = FAVORABLE_PROFILE.model_copy()
        base_result = execute_tool("cotizar", {}, base_ctx)
        assert result["annual_premium"] != base_result["annual_premium"]

    def test_without_profile_returns_controlled_error(self) -> None:
        ctx = ToolContext()
        assert ctx.profile is None

        result = execute_tool("cotizar", {}, ctx)

        assert isinstance(result, dict)
        assert "error" in result


# --- Fase 3: ajustar_comparar + cerrar_venta ---


def _build_full_funnel_ctx(session_id: str = "sesion-test") -> ToolContext:
    """Ejecuta las tools reales, en orden, sobre un mismo ToolContext.

    perfilar_cliente (perfil declarado favorable, equivalente a
    FAVORABLE_PROFILE) -> recomendar_seguro -> cotizar. Deja el ctx en el
    mismo estado que tendría al final del funnel de cotización, listo para
    ajustar_comparar / cerrar_venta.
    """
    ctx = ToolContext(session_id=session_id)
    execute_tool(
        "perfilar_cliente",
        {
            "property_type": "house",
            "zone": "urban",
            "stratum": 3,
            "age_range": "26-40",
        },
        ctx,
    )
    execute_tool("recomendar_seguro", {}, ctx)
    execute_tool("cotizar", {}, ctx)
    return ctx


class TestToolDeclarationsPhase3:
    def test_includes_ajustar_comparar_and_cerrar_venta(self) -> None:
        declarations = tool_declarations()
        names = [decl["name"] for decl in declarations]

        assert "ajustar_comparar" in names
        assert "cerrar_venta" in names

    def test_has_six_unique_declarations_with_required_keys(self) -> None:
        declarations = tool_declarations()
        names = [decl["name"] for decl in declarations]

        assert len(declarations) == 6
        assert len(names) == len(set(names))
        for decl in declarations:
            assert "name" in decl
            assert "description" in decl
            assert "parameters" in decl
            assert isinstance(decl["parameters"], dict)
            assert decl["parameters"].get("type") == "object"


class TestAjustarComparar:
    def test_matches_quote_engine_and_updates_ctx(self) -> None:
        ctx = _build_full_funnel_ctx()
        actual_quote_before = dict(ctx.quote)

        product = CatalogService().get_product("hogar-estandar")
        assert product is not None
        assert len(product.adjustments) >= 1
        adjustment_code = product.adjustments[0].code

        result = execute_tool(
            "ajustar_comparar", {"adjustments": [adjustment_code]}, ctx
        )

        assert set(result.keys()) >= {
            "actual",
            "propuesta",
            "diferencia_mensual",
            "ajustes_disponibles",
        }

        assert (
            result["actual"]["monthly_premium"]
            == actual_quote_before["monthly_premium"]
        )

        expected = QuoteService().calculate_quote(
            FAVORABLE_PROFILE, [adjustment_code]
        )
        assert (
            result["propuesta"]["monthly_premium"]
            == expected["monthly_premium"]
        )

        expected_diff = round(
            result["propuesta"]["monthly_premium"]
            - result["actual"]["monthly_premium"],
            2,
        )
        assert result["diferencia_mensual"] == expected_diff

        codes_disponibles = [
            item.get("code") for item in result["ajustes_disponibles"]
        ]
        assert adjustment_code in codes_disponibles
        for item in result["ajustes_disponibles"]:
            assert set(item.keys()) >= {"code", "name", "description"}

        assert ctx.quote is not None
        assert (
            ctx.quote["monthly_premium"] == result["propuesta"]["monthly_premium"]
        )

    def test_result_is_json_safe(self) -> None:
        ctx = _build_full_funnel_ctx()
        product = CatalogService().get_product("hogar-estandar")
        assert product is not None
        adjustment_code = product.adjustments[0].code

        result = execute_tool(
            "ajustar_comparar", {"adjustments": [adjustment_code]}, ctx
        )

        json.dumps(result)


class TestAjustarCompararSinCotizacion:
    def test_without_prior_quote_returns_controlled_error(self) -> None:
        ctx = ToolContext(session_id="sesion-test")
        ctx.profile = FAVORABLE_PROFILE.model_copy()
        assert ctx.quote is None

        result = execute_tool("ajustar_comparar", {"adjustments": []}, ctx)

        assert isinstance(result, dict)
        assert "error" in result


class TestCerrarVenta:
    # Nota (ajuste E1/Fase 2): `cerrar_venta` ahora exige `email` (además de
    # `consentimiento`) para cerrar — se agrega un correo válido al guion y
    # se mockea `resend_client.send_email` (cero red real) para no romper
    # estos tests que ejercitan el camino feliz de cierre. El detalle del
    # correo lo cubre `tests/test_handoff_flow.py`; aquí solo se evita que el
    # nuevo parámetro requerido tumbe estos tests preexistentes.
    def test_consent_true_reaches_ready_for_payment_with_intact_price(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            resend_client, "send_email", lambda *a, **k: {"ok": True, "id": "x"}
        )
        ctx = _build_full_funnel_ctx()
        premium_before_close = ctx.quote["monthly_premium"]

        result = execute_tool(
            "cerrar_venta",
            {"consentimiento": True, "email": "cliente@example.com"},
            ctx,
        )

        assert result["state"] == "ready_for_payment"
        assert result.get("consent_timestamp")
        assert result["session_id"] == "sesion-test"
        assert result.get("product_id")
        assert result["quote"]["monthly_premium"] == premium_before_close

    def test_result_is_json_safe(self, monkeypatch) -> None:
        monkeypatch.setattr(
            resend_client, "send_email", lambda *a, **k: {"ok": True, "id": "x"}
        )
        ctx = _build_full_funnel_ctx()

        result = execute_tool(
            "cerrar_venta",
            {"consentimiento": True, "email": "cliente@example.com"},
            ctx,
        )

        json.dumps(result)


class TestCerrarVentaConsentimientoFalso:
    def test_consent_false_returns_controlled_error(self) -> None:
        ctx = _build_full_funnel_ctx()

        result = execute_tool(
            "cerrar_venta", {"consentimiento": False}, ctx
        )

        assert isinstance(result, dict)
        assert "error" in result


class TestCerrarVentaSinCotizacionPrevia:
    def test_missing_quote_returns_controlled_error_mentioning_quote(
        self,
    ) -> None:
        ctx = ToolContext(session_id="sesion-test")
        ctx.profile = FAVORABLE_PROFILE.model_copy()
        assert ctx.quote is None

        result = execute_tool(
            "cerrar_venta", {"consentimiento": True}, ctx
        )

        assert isinstance(result, dict)
        assert "error" in result
        text = (
            f"{result.get('error', '')} {result.get('detail', '')}"
        ).lower()
        assert "cotiz" in text


class TestFunnelEndToEndSinLLM:
    """Mini-e2e del contrato de tools sin LLM, sobre un mismo ToolContext."""

    def test_full_funnel_via_execute_tool_reaches_ready_for_payment(
        self, monkeypatch
    ) -> None:
        # Ajuste E1/Fase 2: `cerrar_venta` exige `email` — se agrega uno
        # válido y se mockea `resend_client.send_email` (cero red real).
        monkeypatch.setattr(
            resend_client, "send_email", lambda *a, **k: {"ok": True, "id": "x"}
        )
        ctx = ToolContext(session_id="sesion-test")

        perfilar_result = execute_tool(
            "perfilar_cliente",
            {
                "property_type": "house",
                "zone": "urban",
                "stratum": 3,
                "age_range": "26-40",
            },
            ctx,
        )
        recomendar_result = execute_tool("recomendar_seguro", {}, ctx)
        cotizar_result = execute_tool("cotizar", {}, ctx)

        product = CatalogService().get_product("hogar-estandar")
        assert product is not None
        adjustment_code = product.adjustments[0].code
        ajustar_result = execute_tool(
            "ajustar_comparar", {"adjustments": [adjustment_code]}, ctx
        )
        cerrar_result = execute_tool(
            "cerrar_venta",
            {"consentimiento": True, "email": "cliente@example.com"},
            ctx,
        )

        for result in (
            perfilar_result,
            recomendar_result,
            cotizar_result,
            ajustar_result,
            cerrar_result,
        ):
            assert "error" not in result

        assert cerrar_result["state"] == "ready_for_payment"


# --- Fase 3 (B3): coherencia del funnel multicategoría -----------------------
#
# TDD-light, RED antes de implementar: el motor de propensión (B3) ya
# recomienda entre 5 categorías (`PropensityService.evaluate`), pero
# `_cotizar`/`_ajustar_comparar` de `agent_tools.py` todavía cotizan/ajustan
# siempre contra "hogar-estandar", sin mirar `ctx.recommendation`. Estos
# tests describen el comportamiento objetivo tras la Fase 3 — el funnel debe
# cotizar, listar ajustes y cerrar la venta sobre el producto que el motor
# recomendó, con fallback a "hogar-estandar" cuando se cotiza sin recomendar
# antes. Fallan hoy por la razón correcta (el código de producción aún no
# resuelve el product_id del contexto).

MOVILIDAD_PROFILE = ProfileData(age_range="26-40", has_vehicle=True)
CREDITO_PROFILE = ProfileData(age_range="41-55", has_credit=True)
HOGAR_DIRECTO_PROFILE = ProfileData(
    property_type="house", zone="urban", stratum=3, age_range="26-40"
)


class TestFunnelCoherenteMulticategoria:
    def test_cotizar_usa_producto_recomendado(self) -> None:
        ctx = ToolContext(session_id="s-movilidad")
        ctx.profile = MOVILIDAD_PROFILE.model_copy()

        recomendar_result = execute_tool("recomendar_seguro", {}, ctx)
        assert recomendar_result["product_id"] == "movilidad-auto"

        result = execute_tool("cotizar", {}, ctx)

        assert result["product_id"] == "movilidad-auto"
        assert result["monthly_premium"] == 120000.0

    def test_cotizar_sin_recomendacion_cae_a_hogar(self) -> None:
        ctx = ToolContext(session_id="s-hogar-directo")
        ctx.profile = HOGAR_DIRECTO_PROFILE.model_copy()
        assert ctx.recommendation is None

        result = execute_tool("cotizar", {}, ctx)

        assert "error" not in result
        assert result["product_id"] == "hogar-estandar"
        assert result["monthly_premium"] == 3750.0

    def test_ajustar_comparar_lista_ajustes_del_producto_recomendado(
        self,
    ) -> None:
        ctx = ToolContext(session_id="s-movilidad-ajustes")
        ctx.profile = MOVILIDAD_PROFILE.model_copy()
        execute_tool("recomendar_seguro", {}, ctx)
        execute_tool("cotizar", {}, ctx)

        result = execute_tool("ajustar_comparar", {"adjustments": []}, ctx)

        product = CatalogService().get_product("movilidad-auto")
        assert product is not None
        expected_codes = {adj.code for adj in product.adjustments}

        result_codes = {
            item["code"] for item in result["ajustes_disponibles"]
        }
        assert result_codes == expected_codes
        assert "fire_alarm" not in result_codes

    def test_cerrar_venta_cierra_con_producto_recomendado(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            resend_client, "send_email", lambda *a, **k: {"ok": True, "id": "x"}
        )
        ctx = ToolContext(session_id="s-credito")
        ctx.profile = CREDITO_PROFILE.model_copy()

        recomendar_result = execute_tool("recomendar_seguro", {}, ctx)
        assert recomendar_result["product_id"] == "credito-vida-deudor"
        execute_tool("cotizar", {}, ctx)

        result = execute_tool(
            "cerrar_venta",
            {"consentimiento": True, "email": "x@y.co"},
            ctx,
        )

        assert result["product_id"] == "credito-vida-deudor"
        assert (
            result["recommendation"]["product_name"] == "Crédito Vida Deudor"
        )


# --- Fase 3 (C2): fusión base sintética + declarado en perfilar_cliente ------
#
# TDD-light, RED antes de implementar: `_perfilar_cliente` todavía no fusiona
# las señales sintéticas de la BD (`AffiliateRecord.sint_*`, mapeadas a
# has_children/has_vehicle/has_credit/property_type en `AffiliateProfile` por
# `AffiliateRepository._record_to_profile`) con lo declarado en la
# conversación. Estos tests describen el comportamiento objetivo: declarado
# gana; si el campo declarado es None, se usa el de la base. Fallan hoy por
# la razón correcta (el código de producción aún ignora esas señales del
# perfil resuelto).
#
# `AffiliateService()` (usada internamente por `_perfilar_cliente`) crea un
# `AffiliateRepository()` sin engine explícito, que resuelve el engine vía
# `app.repositories.db.get_engine()` — se monkeypatchea esa función para
# apuntar a un SQLite in-memory propio de cada test, sin depender del engine
# global de la app.


class TestPerfilarClienteConBaseSintetica:
    def setup_method(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        init_db(self.engine)
        with Session(self.engine) as session:
            session.add(
                AffiliateRecord(
                    serie="S888",
                    age_range="26-40",
                    household_segment="RHO",
                    sint_tiene_vehiculo=True,
                    sint_tiene_credito=False,
                    sint_tiene_hijos=False,
                    sint_tipo_vivienda="apartment",
                )
            )
            session.commit()

    def test_serie_real_arma_perfil_con_senales_sin_preguntar(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        ctx = ToolContext(session_id="s-sintetico-1")

        result = execute_tool(
            "perfilar_cliente", {"document_number": "S888"}, ctx
        )

        assert result["afiliado"] is True
        assert ctx.profile.has_vehicle is True
        assert ctx.profile.property_type == "apartment"

    def test_serie_real_recomienda_movilidad_sin_declarar(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        ctx = ToolContext(session_id="s-sintetico-2")

        execute_tool("perfilar_cliente", {"document_number": "S888"}, ctx)
        result = execute_tool("recomendar_seguro", {}, ctx)

        assert result["product_id"] == "movilidad-auto"
        codes = {reason["code"] for reason in result["reasons"]}
        assert "vehicle_declared" in codes

    def test_declarado_pisa_sintetico(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        ctx = ToolContext(session_id="s-sintetico-3")

        execute_tool(
            "perfilar_cliente",
            {"document_number": "S888", "has_vehicle": False},
            ctx,
        )

        assert ctx.profile.has_vehicle is False

    def test_no_afiliado_sigue_flujo_declarado(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        ctx = ToolContext(session_id="s-sintetico-4")

        result = execute_tool(
            "perfilar_cliente", {"has_credit": True}, ctx
        )

        assert ctx.profile.has_credit is True
        assert result["fuente"] == "declarado"


# --- Fase 2 (A4): enriquecer_perfil ------------------------------------------
#
# TDD-light, RED antes de implementar: la tool `enriquecer_perfil` todavía no
# existe en `AGENT_TOOLS`. Estos tests describen el comportamiento objetivo:
# persiste el dato declarado vía `EnrichmentService` (el mismo motor de
# `app/services/enrichment.py`, ya implementado y probado en
# `test_enrichment.py`) y, cuando el campo tiene un mapeo directo al perfil en
# memoria (hijos, vehiculo, credito, tipo_vivienda), también actualiza
# `ctx.profile` para que el motor de propensión (`recomendar_seguro`) vea el
# dato enriquecido de inmediato, sin esperar a un nuevo `perfilar_cliente`.
#
# Engine: SQLite in-memory + `init_db`, con `app.repositories.db.get_engine`
# monkeypatcheado — mismo patrón que `TestPerfilarClienteConBaseSintetica`.


class TestEnriquecerPerfil:
    def setup_method(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        init_db(self.engine)

    def test_declaracion_registrada(self) -> None:
        declarations = tool_declarations()
        names = [decl["name"] for decl in declarations]
        assert "enriquecer_perfil" in names

        enriquecer = next(
            decl
            for decl in declarations
            if decl["name"] == "enriquecer_perfil"
        )
        properties = enriquecer["parameters"]["properties"]

        assert set(properties["campo"]["enum"]) == {
            "hijos",
            "mascota",
            "vehiculo",
            "credito",
            "fumador",
            "ocupacion",
            "tipo_vivienda",
        }
        assert set(enriquecer["parameters"]["required"]) >= {"campo", "valor"}

    def test_criterio1_hijos_y_mascota_persisten(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        ctx = ToolContext(session_id="sess-e1")

        result_hijos = execute_tool(
            "enriquecer_perfil", {"campo": "hijos", "valor": "2"}, ctx
        )
        result_mascota = execute_tool(
            "enriquecer_perfil", {"campo": "mascota", "valor": "perro"}, ctx
        )

        assert EnrichmentService(engine=self.engine).fields_for("sess-e1") == {
            "hijos": "2",
            "mascota": "perro",
        }
        assert ctx.profile.children_count == 2
        assert ctx.profile.has_children is True
        assert result_hijos["persistido"] is True
        assert result_mascota["persistido"] is True

    def test_criterio2_dato_enriquecido_cambia_recomendacion(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        ctx = ToolContext(session_id="sess-e2")
        ctx.profile = ProfileData(
            age_range="26-40",
            property_type="house",
            zone="urban",
            stratum=3,
        )

        before = execute_tool("recomendar_seguro", {}, ctx)
        assert before["product_id"] == "hogar-estandar"

        execute_tool(
            "enriquecer_perfil", {"campo": "vehiculo", "valor": "si"}, ctx
        )

        result = execute_tool("recomendar_seguro", {}, ctx)

        assert result["product_id"] == "movilidad-auto"
        codes = {reason["code"] for reason in result["reasons"]}
        assert "vehicle_declared" in codes

    def test_evidencia_cita_numero_de_hijos(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        ctx = ToolContext(session_id="sess-e3")
        ctx.profile = ProfileData(age_range="26-40")

        execute_tool(
            "enriquecer_perfil", {"campo": "hijos", "valor": "2"}, ctx
        )
        result = execute_tool("recomendar_seguro", {}, ctx)

        vida_entry = next(
            entry for entry in result["ranking"] if entry["category"] == "vida"
        )
        dependents_reason = next(
            reason
            for reason in vida_entry["reasons"]
            if reason["code"] == "dependents"
        )
        assert "2" in dependents_reason["evidence"]

    def test_campo_desconocido_error_controlado(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        ctx = ToolContext(session_id="sess-e4")

        result = execute_tool(
            "enriquecer_perfil", {"campo": "color", "valor": "azul"}, ctx
        )

        assert isinstance(result, dict)
        assert "error" in result

    def test_valor_invalido_error_controlado(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        ctx = ToolContext(session_id="sess-e5")

        result = execute_tool(
            "enriquecer_perfil", {"campo": "hijos", "valor": "perro"}, ctx
        )

        assert isinstance(result, dict)
        assert "error" in result

    def test_sin_perfil_previo_crea_perfil(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        ctx = ToolContext(session_id="sess-e6")
        assert ctx.profile is None

        execute_tool(
            "enriquecer_perfil", {"campo": "vehiculo", "valor": "si"}, ctx
        )

        assert ctx.profile is not None
        assert ctx.profile.has_vehicle is True

    def test_resultado_json_safe(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        ctx = ToolContext(session_id="sess-e7")

        result = execute_tool(
            "enriquecer_perfil", {"campo": "hijos", "valor": "2"}, ctx
        )

        json.dumps(result)


# --- Fase 3 (A4): memoria cross-sesión por SERIE en perfilar_cliente --------
#
# TDD-light, RED antes de implementar: `_perfilar_cliente` todavía no
# consulta `EnrichmentService().fields_for(ctx.session_id, serie=document_number)`
# al resolver el perfil base — hoy solo usa lo declarado en el turno actual y
# lo que trae `AffiliateService.resolve` (base real o sintética). Estos tests
# describen el comportamiento objetivo: cuando el mismo `document_number`
# (serie) reaparece en una sesión nueva, lo enriquecido previamente en OTRA
# sesión para esa serie debe aplicarse al perfil, con la prioridad declarado
# ahora > enriquecido previo > base real/sintética. Fallan hoy por la razón
# correcta (el código de producción aún no lee la memoria cross-sesión por
# serie).
#
# Mismo patrón de setup que `TestEnriquecerPerfil` /
# `TestPerfilarClienteConBaseSintetica`: engine SQLite in-memory + `init_db`,
# con `app.repositories.db.get_engine` monkeypatcheado.


class TestMemoriaCrossSesionPorSerie:
    def setup_method(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        init_db(self.engine)

    def test_serie_recupera_enriquecido_en_sesion_nueva(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)

        ctx_a = ToolContext(session_id="sess-a")
        execute_tool(
            "perfilar_cliente", {"document_number": "S900"}, ctx_a
        )
        execute_tool(
            "enriquecer_perfil", {"campo": "vehiculo", "valor": "si"}, ctx_a
        )

        ctx_b = ToolContext(session_id="sess-b")
        execute_tool(
            "perfilar_cliente", {"document_number": "S900"}, ctx_b
        )

        assert ctx_b.profile.has_vehicle is True

        result = execute_tool("recomendar_seguro", {}, ctx_b)

        assert result["product_id"] == "movilidad-auto"

    def test_enriquecido_pisa_base_sintetica(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        with Session(self.engine) as session:
            session.add(
                AffiliateRecord(
                    serie="S901",
                    age_range="26-40",
                    sint_tiene_vehiculo=True,
                )
            )
            session.commit()

        ctx_a = ToolContext(session_id="sess-a")
        execute_tool(
            "perfilar_cliente", {"document_number": "S901"}, ctx_a
        )
        execute_tool(
            "enriquecer_perfil", {"campo": "vehiculo", "valor": "no"}, ctx_a
        )

        ctx_b = ToolContext(session_id="sess-b")
        execute_tool(
            "perfilar_cliente", {"document_number": "S901"}, ctx_b
        )

        assert ctx_b.profile.has_vehicle is False

    def test_declarado_ahora_pisa_enriquecido(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)

        ctx_a = ToolContext(session_id="sess-a")
        execute_tool(
            "perfilar_cliente", {"document_number": "S902"}, ctx_a
        )
        execute_tool(
            "enriquecer_perfil", {"campo": "vehiculo", "valor": "si"}, ctx_a
        )

        ctx_b = ToolContext(session_id="sess-b")
        execute_tool(
            "perfilar_cliente",
            {"document_number": "S902", "has_vehicle": False},
            ctx_b,
        )

        assert ctx_b.profile.has_vehicle is False

    def test_hijos_enriquecidos_llegan_con_numero(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)

        ctx_a = ToolContext(session_id="sess-a")
        execute_tool(
            "perfilar_cliente", {"document_number": "S903"}, ctx_a
        )
        execute_tool(
            "enriquecer_perfil", {"campo": "hijos", "valor": "2"}, ctx_a
        )

        ctx_b = ToolContext(session_id="sess-b")
        execute_tool(
            "perfilar_cliente", {"document_number": "S903"}, ctx_b
        )

        assert ctx_b.profile.children_count == 2
        assert ctx_b.profile.has_children is True

    def test_sin_documento_sin_cambios(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        ctx = ToolContext(session_id="sess-sin-doc")

        result = execute_tool(
            "perfilar_cliente", {"property_type": "house"}, ctx
        )

        assert result["afiliado"] is False
        assert result["fuente"] == "declarado"
        assert ctx.profile.property_type == "house"
