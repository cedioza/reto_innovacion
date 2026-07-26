"""Script de carga batch del dataset real de afiliados a la tabla `afiliados`.

Reusa el parser de `AffiliateRepository` (CSV y xlsx, con la normalización
de rangos/segmentos de la Fase 1) y decora cada perfil con las columnas
sintéticas deterministas de `app.services.synthetic.synthetic_for` antes de
insertar en lotes.

Uso (desde `backend/`, con el venv activo):

    python -m app.scripts.cargar_afiliados <ruta al csv o xlsx> [--replace]

La ruta al archivo real NUNCA se commitea al repo (contiene datos de
afiliados); solo vive en la máquina/entorno donde se ejecuta la carga.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, insert
from sqlalchemy import Engine

from app.models.affiliate_record import AffiliateRecord
from app.repositories import db
from app.repositories.affiliates import AffiliateRepository
from app.services.synthetic import synthetic_for

_BATCH_SIZE = 5000


def load_to_db(path: str, engine: Engine | None = None, replace: bool = False) -> dict:
    """Parsea `path` (CSV/xlsx) y carga los perfiles en la tabla `afiliados`.

    Reusa `AffiliateRepository.load_from_csv` para el parseo y accede a los
    perfiles resultantes vía el accesor público `parsed_profiles()` (evita
    tocar el diccionario interno `_profiles` del repositorio).

    Devuelve un resumen `{"loaded": n, "parse_errors": n, "seconds": float}`.
    """
    resolved_engine = engine or db.get_engine()
    db.init_db(resolved_engine)  # idempotente: create_all si no existen

    started = time.perf_counter()

    repo = AffiliateRepository(csv_path=path)
    repo.load_from_csv(path)
    profiles = repo.parsed_profiles()

    now = datetime.now(timezone.utc)
    rows = []
    for profile in profiles.values():
        row = {
            "serie": profile.document_number,
            "age_range": profile.age_range,
            "gender": profile.gender,
            "salary_range": profile.salary_range,
            "category": profile.category,
            "household_segment": profile.household_segment,
            "population_segment": profile.population_segment,
            "pyramid": profile.pyramid,
            "empresa_foco": profile.empresa_foco,
            "city": profile.city,
            "uses_hoteles": profile.uses_hoteles,
            "uses_piscilago": profile.uses_piscilago,
            "uses_drogueria": profile.uses_drogueria,
            "uses_agencias": profile.uses_agencias,
            "uses_vivienda": profile.uses_vivienda,
            "loaded_at": now,
            **synthetic_for(profile),
        }
        rows.append(row)

    with resolved_engine.begin() as conn:
        if replace:
            conn.execute(delete(AffiliateRecord))
        for start in range(0, len(rows), _BATCH_SIZE):
            batch = rows[start : start + _BATCH_SIZE]
            if batch:
                conn.execute(insert(AffiliateRecord), batch)

    seconds = time.perf_counter() - started

    return {
        "loaded": len(rows),
        "parse_errors": len(repo.load_errors),
        "seconds": seconds,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Carga el dataset real de afiliados (CSV/xlsx) en la tabla "
            "`afiliados`."
        )
    )
    parser.add_argument(
        "path",
        help="Ruta al archivo CSV o xlsx del dataset real de afiliados.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Borra los registros existentes de `afiliados` antes de cargar.",
    )
    args = parser.parse_args(argv)

    if not Path(args.path).exists():
        print(f"error: no se encontró el archivo '{args.path}'", file=sys.stderr)
        sys.exit(2)

    summary = load_to_db(args.path, replace=args.replace)

    print(
        f"cargados: {summary['loaded']} | "
        f"errores de parseo: {summary['parse_errors']} | "
        f"tiempo: {summary['seconds']:.2f}s"
    )
    print("recuerda: la fuente (CSV/xlsx real) NUNCA se commitea al repo.")


if __name__ == "__main__":
    main()
