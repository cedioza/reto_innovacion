"""Script de curaduría de SERIEs candidatas para los guiones de demo (H4).

Recorre la tabla `afiliados` (paginada por `serie` ascendente, en lotes) y,
por cada registro, arma el `AffiliateProfile` correspondiente y lo evalúa con
`PropensityService.evaluate()`. Un perfil solo se propone como candidato de
demo de la categoría ganadora de su `ranking` si esa categoría le saca un
margen de al menos 0.10 a la segunda posición del ranking.

¿Por qué 0.10 y no "el que gane, gana"? Porque en la demo el afiliado
conversa y puede declarar, de viva voz, un dato adicional (p. ej. "también
tengo carro" o "no tengo hijos") que el motor no conocía de antemano. Un
perfil cuyo margen entre el primer y el segundo puesto es chico es un
ranking frágil: ese único dato declarado en conversación podría voltear la
categoría ganadora en pleno demo. Exigir un margen mínimo filtra esos casos
ambiguos y deja solo perfiles cuya categoría ganadora es robusta frente a lo
que el afiliado pueda decir en vivo.

Uso (desde `backend/`, con el venv activo):

    python -m app.scripts.curar_series [--candidatos-por-categoria N] [--max-filas N]

Las SERIEs reales que arroje este script van a la nota interna del vault del
equipo (fuera del repo) para preparar los guiones de demo — NUNCA se
commitean ni se imprimen en un log que termine en el repositorio.
"""

from __future__ import annotations

import argparse

from sqlmodel import Session, select

from app.models.affiliate_record import AffiliateRecord
from app.repositories import db
from app.repositories.affiliates import AffiliateRepository
from app.services.catalog import CatalogService
from app.services.propensity import PropensityService

_BATCH_SIZE = 1000
_MARGIN_THRESHOLD = 0.10


def _ordered_categories() -> list[str]:
    """Categorías del catálogo, en el orden en que aparecen (una vez cada una)."""
    categories: list[str] = []
    for product in CatalogService().list_products():
        if product.category not in categories:
            categories.append(product.category)
    return categories


def curar(
    engine=None,
    candidatos_por_categoria: int = 3,
    max_filas: int = 100000,
) -> dict[str, list[dict]]:
    """Curaduría de SERIEs candidatas por categoría, para guiones de demo.

    Recorre `afiliados` en lotes ordenados por `serie` ascendente (keyset
    pagination), evalúa cada perfil una única vez con `PropensityService` y
    acumula, por categoría del catálogo, hasta `candidatos_por_categoria`
    perfiles cuyo margen entre el primer y el segundo puesto del ranking sea
    >= 0.10. Se detiene al llegar a `max_filas` filas procesadas o antes, si
    ya se llenó el cupo de las cinco categorías (early-stop).

    Devuelve un dict con una clave por categoría del catálogo (incluso si
    quedó vacía), cada una con una lista de a lo sumo
    `candidatos_por_categoria` dicts:
    `{"serie", "score", "reasons", "runner_up": {"category", "score"}, "margin"}`.
    """
    resolved_engine = engine or db.get_engine()
    service = PropensityService()

    categories = _ordered_categories()
    candidates: dict[str, list[dict]] = {category: [] for category in categories}

    processed = 0
    last_serie: str | None = None

    with Session(resolved_engine) as session:
        while processed < max_filas:
            remaining = max_filas - processed
            statement = select(AffiliateRecord).order_by(AffiliateRecord.serie)
            if last_serie is not None:
                statement = statement.where(AffiliateRecord.serie > last_serie)
            statement = statement.limit(min(_BATCH_SIZE, remaining))

            rows = session.exec(statement).all()
            if not rows:
                break

            for record in rows:
                processed += 1
                last_serie = record.serie

                profile = AffiliateRepository.record_to_profile(record)
                evaluation = service.evaluate(profile)
                ranking = evaluation["ranking"]
                winner = ranking[0]
                runner_up = ranking[1]
                margin = round(winner["score"] - runner_up["score"], 2)

                if margin >= _MARGIN_THRESHOLD:
                    bucket = candidates.get(winner["category"])
                    if bucket is not None and len(bucket) < candidatos_por_categoria:
                        bucket.append(
                            {
                                "serie": record.serie,
                                "score": winner["score"],
                                "reasons": winner["reasons"],
                                "runner_up": {
                                    "category": runner_up["category"],
                                    "score": runner_up["score"],
                                },
                                "margin": margin,
                            }
                        )

                if processed >= max_filas:
                    break

            if all(
                len(candidates[category]) >= candidatos_por_categoria
                for category in categories
            ):
                break

    return candidates


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Cura SERIEs candidatas por categoría para guiones de demo, a "
            "partir del ranking de propensión de cada afiliado."
        )
    )
    parser.add_argument(
        "--candidatos-por-categoria",
        type=int,
        default=3,
        help="Máximo de candidatos a devolver por categoría (default: 3).",
    )
    parser.add_argument(
        "--max-filas",
        type=int,
        default=100000,
        help="Máximo de filas de `afiliados` a recorrer (default: 100000).",
    )
    args = parser.parse_args(argv)

    resultado = curar(
        candidatos_por_categoria=args.candidatos_por_categoria,
        max_filas=args.max_filas,
    )

    total = 0
    for categoria, candidatos in resultado.items():
        print(f"== {categoria}: {len(candidatos)} candidato(s) ==")
        for candidato in candidatos:
            print(
                f"  serie={candidato['serie']} score={candidato['score']} "
                f"margin={candidato['margin']} "
                f"runner_up={candidato['runner_up']['category']}"
                f"({candidato['runner_up']['score']})"
            )
            for reason in candidato["reasons"]:
                print(f"    - {reason['code']}: {reason['evidence']}")
        total += len(candidatos)

    print(f"total de candidatos: {total}")
    print(
        "recuerda: las SERIEs reales van a la nota interna del vault del "
        "equipo, NUNCA al repo."
    )


if __name__ == "__main__":
    main()
