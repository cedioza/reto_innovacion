"""Affiliate profile repository.

Loads anonymized affiliate data from a CSV file and provides
lookup by document_number (SERIE). The CSV is expected to be
a semicolon-delimited file with columns matching the dataset
schema described in the vault:

  SERIE;GENERO;RANGO_EDAD;RANGO_SALARIO;SEGMENTO_HOGAR;
  SEGMENTO_POBLACION;CIUDAD;SEÑAL_CONSUMO_1..5

Only the first invocation reads the file; subsequent lookups
use an in-memory dictionary.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

from app.models.affiliate import AffiliateProfile

AFFILIATE_CSV_PATH = os.getenv(
    "AFFILIATE_CSV_PATH",
    str(Path(__file__).resolve().parent.parent.parent / "data" / "afiliados.csv"),
)


class AffiliateRepository:
    """Repository backed by an in-memory dict built from CSV."""

    def __init__(self, csv_path: str | None = None) -> None:
        self._csv_path = csv_path or AFFILIATE_CSV_PATH
        self._profiles: dict[str, AffiliateProfile] | None = None

    # -- public API -----------------------------------------------------------

    def find_by_document(self, document_number: str) -> AffiliateProfile | None:
        return self._load()[0].get(document_number)

    def exists(self, document_number: str) -> bool:
        return document_number in self._load()[0]

    def count(self) -> int:
        return len(self._load()[0])

    def load_from_csv(self, path: str) -> int:
        """Load affiliate profiles from a CSV file.

        Args:
            path: Absolute path to the CSV file.

        Returns:
            Number of records loaded.

        Raises:
            FileNotFoundError: If the CSV does not exist.
            csv.Error: If the file is malformed.
        """
        records, errors = self._parse_csv(path)
        self._profiles = records
        return len(records)

    # -- internals ------------------------------------------------------------

    def _load(self) -> tuple[dict[str, AffiliateProfile], list[str]]:
        """Lazy-load CSV on first call."""
        if self._profiles is not None:
            return self._profiles, []
        return self._parse_csv(self._csv_path)

    def _parse_csv(
        self, path: str
    ) -> tuple[dict[str, AffiliateProfile], list[str]]:
        profiles: dict[str, AffiliateProfile] = {}
        errors: list[str] = []

        try:
            with open(path, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f, delimiter=";")
                for row_num, row in enumerate(reader, start=2):
                    serie = (row.get("SERIE") or "").strip()
                    if not serie:
                        errors.append(f"Row {row_num}: missing SERIE")
                        continue
                    try:
                        profile = self._row_to_profile(serie, row)
                        profiles[serie] = profile
                    except (ValueError, TypeError) as exc:
                        errors.append(f"Row {row_num}: {exc}")
        except FileNotFoundError:
            pass  # Graceful fallback — repository returns empty

        self._profiles = profiles
        return profiles, errors

    @staticmethod
    def _row_to_profile(serie: str, row: dict[str, str]) -> AffiliateProfile:
        raw_stratum = (row.get("SEGMENTO_HOGAR") or "").strip()
        stratum = 3
        if raw_stratum:
            try:
                stratum = int(raw_stratum)
            except ValueError:
                stratum = 3  # default when parsing fails

        return AffiliateProfile(
            document_number=serie,
            age_range=(row.get("RANGO_EDAD") or "").strip(),
            stratum=stratum,
            city=(row.get("CIUDAD") or "").strip() or None,
            property_type=None,  # not directly available in dataset
            zone=(
                "urban"
                if (row.get("CIUDAD") or "").strip()
                else "rural"
            ),
            household_segment=(row.get("SEGMENTO_HOGAR") or "").strip() or None,
            population_segment=(
                row.get("SEGMENTO_POBLACION") or ""
            ).strip() or None,
            salary_range=(row.get("RANGO_SALARIO") or "").strip() or None,
        )
