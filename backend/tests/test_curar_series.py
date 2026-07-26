"""Tests for the demo-curation script (plan H4, RED).

`app.scripts.curar_series` expondrá `curar(engine=None,
candidatos_por_categoria=3, max_filas=100000) -> dict[str, list[dict]]` y un
`main(argv)` CLI. `curar` recorre la tabla `afiliados` paginando por `serie`
en orden ascendente, convierte cada fila a `AffiliateProfile`
(`AffiliateRepository._record_to_profile`) y la evalúa con
`PropensityService.evaluate()`: un perfil es candidato de la categoría
ganadora de su `ranking` solo si esa categoría le saca margen >= 0.10 a la
segunda del ranking.

Este módulo se escribe antes de que `app.scripts.curar_series` exista, así
que la colección debe fallar con ImportError/ModuleNotFoundError hasta que
la siguiente tarea lo implemente.

Patrón de engine igual a backend/tests/test_cargar_afiliados.py (SQLite en
memoria, StaticPool, `init_db`); inserción directa de `AffiliateRecord` con
columnas `sint_*` ya fijadas (sin sha256, sin `synthetic_for`).
"""

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app.models.affiliate_record import AffiliateRecord
from app.repositories import db as db_module
from app.repositories.db import init_db
from app.scripts.curar_series import curar, main

CATEGORIES = ("hogar", "vida", "accidentes", "movilidad", "credito")

# -- fixture de perfiles: uno claramente ganador por categoría + uno ambiguo -
# Todos con city="BOGOTA" (=> zone="urban"); los campos sint_* no
# mencionados quedan en False (nunca None, para que las reglas de
# "sin dependientes"/"sin family" tampoco se disparen por accidente).
FIXTURE_PROFILES = {
    # movilidad: vehicle_declared (0.75) domina sobre cualquier otra cosa.
    "MOV001": dict(
        age_range="26-40",
        sint_tiene_vehiculo=True,
        sint_tiene_credito=False,
        sint_tiene_hijos=False,
        sint_tipo_vivienda=None,
    ),
    # credito: credit_declared + working_age (0.80).
    "CRED001": dict(
        age_range="26-40",
        sint_tiene_vehiculo=False,
        sint_tiene_credito=True,
        sint_tiene_hijos=False,
        sint_tipo_vivienda=None,
    ),
    # vida: dependents + life_stage + family_segment (RHO) (0.75).
    "VIDA001": dict(
        age_range="26-40",
        sint_tiene_vehiculo=False,
        sint_tiene_credito=False,
        sint_tiene_hijos=True,
        sint_tipo_vivienda=None,
        household_segment="RHO",
    ),
    # hogar: homeowner (house) + income_tier + zone_risk, sin hijos/vehiculo/
    # credito.
    "HOG001": dict(
        age_range="26-40",
        sint_tiene_vehiculo=False,
        sint_tiene_credito=False,
        sint_tiene_hijos=False,
        sint_tipo_vivienda="house",
    ),
    # accidentes: young_profile + urban_exposure, perfil joven sin nada mas.
    "ACC001": dict(
        age_range="18-25",
        sint_tiene_vehiculo=False,
        sint_tiene_credito=False,
        sint_tiene_hijos=False,
        sint_tipo_vivienda=None,
    ),
    # ambiguo: vehiculo Y credito a la vez -> credito y movilidad casi
    # empatados, margen < 0.10 frente al segundo puesto -> no debe ganar
    # ninguna categoria.
    "AMB001": dict(
        age_range="26-40",
        sint_tiene_vehiculo=True,
        sint_tiene_credito=True,
        sint_tiene_hijos=False,
        sint_tipo_vivienda=None,
    ),
}


def _record(serie: str, **overrides) -> AffiliateRecord:
    fields = dict(FIXTURE_PROFILES[serie])
    fields.update(overrides)
    fields.setdefault("household_segment", None)
    return AffiliateRecord(serie=serie, city="BOGOTA", **fields)


class TestCurarSeries:
    def setup_method(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        init_db(self.engine)

        with Session(self.engine) as session:
            for serie in FIXTURE_PROFILES:
                session.add(_record(serie))
            session.commit()

    # -- un candidato claro por categoria ---------------------------------

    def test_curar_encuentra_candidato_por_categoria(self) -> None:
        resultado = curar(engine=self.engine, candidatos_por_categoria=1)

        assert set(resultado.keys()) == set(CATEGORIES)

        esperado = {
            "movilidad": "MOV001",
            "credito": "CRED001",
            "vida": "VIDA001",
            "hogar": "HOG001",
            "accidentes": "ACC001",
        }
        for categoria, serie_esperada in esperado.items():
            candidatos = resultado[categoria]
            assert len(candidatos) == 1, (categoria, candidatos)
            assert candidatos[0]["serie"] == serie_esperada

    # -- margen minimo respetado ------------------------------------------

    def test_candidato_gana_con_margen(self) -> None:
        resultado = curar(engine=self.engine)

        for categoria in CATEGORIES:
            for candidato in resultado[categoria]:
                assert candidato["margin"] >= 0.10
                assert candidato["score"] > candidato["runner_up"]["score"]

    # -- perfil ambiguo (margen insuficiente) no aparece como candidato ----

    def test_perfil_ambiguo_no_es_candidato(self) -> None:
        resultado = curar(engine=self.engine)

        for categoria in CATEGORIES:
            series = [c["serie"] for c in resultado[categoria]]
            assert "AMB001" not in series

    # -- determinismo -------------------------------------------------------

    def test_curar_es_determinista(self) -> None:
        primero = curar(engine=self.engine)
        segundo = curar(engine=self.engine)

        assert primero == segundo

    # -- tabla vacia no truena ------------------------------------------------

    def test_tabla_vacia_no_truena(self) -> None:
        engine_vacio = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        init_db(engine_vacio)

        resultado = curar(engine=engine_vacio)

        assert set(resultado.keys()) == set(CATEGORIES)
        for categoria in CATEGORIES:
            assert resultado[categoria] == []

    # -- CLI con tabla vacia sale limpio -------------------------------------

    def test_cli_tabla_vacia_sale_limpio(self, monkeypatch, capsys) -> None:
        engine_vacio = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        init_db(engine_vacio)
        monkeypatch.setattr(db_module, "get_engine", lambda: engine_vacio)

        main([])

        captured = capsys.readouterr()
        combined_output = captured.out + captured.err
        assert "0" in combined_output

    # -- respeta el cupo por categoria ---------------------------------------

    def test_respeta_cupo(self) -> None:
        with Session(self.engine) as session:
            for serie in ("MOVCUPO1", "MOVCUPO2", "MOVCUPO3"):
                session.add(
                    AffiliateRecord(
                        serie=serie,
                        city="BOGOTA",
                        age_range="26-40",
                        sint_tiene_vehiculo=True,
                        sint_tiene_credito=False,
                        sint_tiene_hijos=False,
                        sint_tipo_vivienda=None,
                    )
                )
            session.commit()

        resultado = curar(engine=self.engine, candidatos_por_categoria=2)

        assert len(resultado["movilidad"]) <= 2

