"""Tests for the profiling matrix — TDD RED phase.

Covers Fase 1 del plan B5 (`.claude/analysis/plans/
20260725-b5-preguntas-por-categoria-matriz.plan.md`): el módulo nuevo
`app.services.profiling_matrix` (`MATRIX` + `campos_pendientes`), la tool
`campos_pendientes` registrada en `AGENT_TOOLS`, la regla 8 del
`SYSTEM_PROMPT` del orquestador que la menciona, y la persistencia de
`ProfileData.source`/`gender` desde `_perfilar_cliente` (`agent_tools.py`).

`app.services.profiling_matrix` no existe todavía — todos los tests de este
archivo fallan hoy con `ModuleNotFoundError` en el import de módulo. Una vez
exista el módulo (Fase 1, paso 2), algunos tests seguirán en rojo por
`AttributeError`/asserts sobre `ProfileData.source` hasta que ese campo (y
`gender`) se agreguen al schema y `_perfilar_cliente` los persista.
"""

from __future__ import annotations

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app.models.affiliate_record import AffiliateRecord
from app.repositories import db as db_module
from app.repositories.db import init_db
from app.schemas.conversation import ProfileData
from app.services.agent_tools import (
    AGENT_TOOLS,
    ToolContext,
    execute_tool,
    tool_declarations,
)

from app.services.profiling_matrix import MATRIX, campos_pendientes

CATEGORIAS_VALIDAS = {"hogar", "vida", "accidentes", "movilidad", "credito"}


def _campo(items: list[dict], nombre: str) -> dict | None:
    """Busca en una lista de `conocidos`/`pendientes` el dict con `campo == nombre`."""
    return next((item for item in items if item["campo"] == nombre), None)


class TestMatrixShape:
    def test_matrix_tiene_exactamente_las_cinco_categorias(self) -> None:
        assert set(MATRIX.keys()) == CATEGORIAS_VALIDAS

    def test_cada_campo_tiene_las_cuatro_llaves_y_fuente_valida(self) -> None:
        fuentes_validas = {"base", "preguntar", "api_simulada"}

        for categoria, campos in MATRIX.items():
            assert isinstance(campos, list)
            assert len(campos) >= 1, f"{categoria} no tiene campos"
            for campo in campos:
                assert set(campo.keys()) >= {
                    "campo",
                    "pregunta_sugerida",
                    "fuente_afiliado",
                    "atributo_perfil",
                }
                assert campo["fuente_afiliado"] in fuentes_validas, campo


class TestCamposPendientes:
    def test_categoria_invalida_lanza_value_error(self) -> None:
        profile = ProfileData(source="declarado")

        with pytest.raises(ValueError):
            campos_pendientes("mascotas", profile)

    def test_afiliado_vida_conocidos_desde_base_criterio_1(self) -> None:
        """Criterio 1 de la Matriz: afiliado con datos ya conocidos en base."""
        profile = ProfileData(
            source="base", age_range="20-35", gender="F", stratum=3
        )

        resultado = campos_pendientes("vida", profile)

        pendientes_campos = {item["campo"] for item in resultado["pendientes"]}
        conocidos_por_campo = {item["campo"]: item for item in resultado["conocidos"]}

        assert not pendientes_campos & {"edad", "genero", "ocupacion", "ingresos"}
        for campo in ("edad", "genero", "ocupacion", "ingresos"):
            assert campo in conocidos_por_campo, f"{campo} debería ser conocido"
            assert "base" in conocidos_por_campo[campo]["fuente"]

        assert "fumador" in pendientes_campos
        assert "deportes_extremos" in pendientes_campos

    def test_prospecto_declarado_vacio_todo_pendiente_criterio_3(self) -> None:
        """Criterio 3 de la Matriz: prospecto que declara, sin nada aún conocido."""
        profile = ProfileData(source="declarado")

        for categoria, campos in MATRIX.items():
            resultado = campos_pendientes(categoria, profile)

            assert resultado["conocidos"] == []
            pendientes_campos = {item["campo"] for item in resultado["pendientes"]}
            esperados = {campo["campo"] for campo in campos}
            assert pendientes_campos == esperados, categoria

    def test_prospecto_declara_edad_y_tipo_inmueble_pasan_a_conocidos(self) -> None:
        profile = ProfileData(
            source="declarado", age_range="26-40", property_type="apartment"
        )

        for categoria in ("vida", "movilidad", "accidentes", "credito"):
            resultado = campos_pendientes(categoria, profile)
            edad_conocido = _campo(resultado["conocidos"], "edad")
            assert edad_conocido is not None, categoria
            assert edad_conocido["fuente"] == "declarado"
            assert _campo(resultado["pendientes"], "edad") is None

        resultado_hogar = campos_pendientes("hogar", profile)
        tipo_inmueble_conocido = _campo(resultado_hogar["conocidos"], "tipo_inmueble")
        assert tipo_inmueble_conocido is not None
        assert tipo_inmueble_conocido["fuente"] == "declarado"
        assert _campo(resultado_hogar["pendientes"], "tipo_inmueble") is None


class TestCamposPendientesTool:
    def test_registrada_en_agent_tools(self) -> None:
        assert "campos_pendientes" in AGENT_TOOLS

    def test_declaracion_registrada_en_tool_declarations(self) -> None:
        declarations = tool_declarations()
        nombres = [decl["name"] for decl in declarations]
        assert "campos_pendientes" in nombres

        declaracion = next(
            decl for decl in declarations if decl["name"] == "campos_pendientes"
        )
        assert "categoria" in declaracion["parameters"]["properties"]
        assert "categoria" in declaracion["parameters"].get("required", [])

    def test_sin_perfil_devuelve_error_controlado(self) -> None:
        ctx = ToolContext(session_id="s1")

        resultado = execute_tool("campos_pendientes", {"categoria": "vida"}, ctx)

        assert isinstance(resultado, dict)
        assert "error" in resultado

    def test_con_perfil_devuelve_conocidos_y_pendientes(self) -> None:
        ctx = ToolContext(session_id="s1")
        ctx.profile = ProfileData(source="declarado", age_range="26-40")

        resultado = execute_tool("campos_pendientes", {"categoria": "vida"}, ctx)

        assert isinstance(resultado, dict)
        assert "error" not in resultado
        assert "conocidos" in resultado
        assert "pendientes" in resultado

    def test_categoria_no_soportada_devuelve_error_sin_excepcion(self) -> None:
        ctx = ToolContext(session_id="s1")
        ctx.profile = ProfileData(source="declarado")

        resultado = execute_tool("campos_pendientes", {"categoria": "mascotas"}, ctx)

        assert isinstance(resultado, dict)
        assert "error" in resultado


class TestSystemPromptRule:
    def test_system_prompt_menciona_campos_pendientes(self) -> None:
        from app.services.orchestrator import SYSTEM_PROMPT

        assert "campos_pendientes" in SYSTEM_PROMPT


class TestSourcePersistence:
    """`_perfilar_cliente` (vía `execute_tool`) debe marcar `profile.source`."""

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
                    serie="S900",
                    age_range="26-40",
                    gender="F",
                    household_segment="RHO",
                )
            )
            session.commit()

    def test_documento_afiliado_marca_source_base_y_gender(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        ctx = ToolContext(session_id="s-source-1")

        execute_tool("perfilar_cliente", {"document_number": "S900"}, ctx)

        assert ctx.profile is not None
        assert ctx.profile.source == "base"
        assert ctx.profile.gender == "F"

    def test_sin_documento_con_declarado_marca_source_declarado(self) -> None:
        ctx = ToolContext(session_id="s-source-2")

        execute_tool(
            "perfilar_cliente",
            {"property_type": "house", "zone": "urban"},
            ctx,
        )

        assert ctx.profile is not None
        assert ctx.profile.source == "declarado"
