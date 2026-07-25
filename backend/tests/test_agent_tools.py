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

from app.core.config import settings
from app.schemas.conversation import ProfileData

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


class TestExecuteToolUnknownName:
    def test_unknown_tool_returns_error_dict_without_raising(self) -> None:
        ctx = ToolContext()

        result = execute_tool("tool_inexistente", {}, ctx)

        assert isinstance(result, dict)
        assert "error" in result
