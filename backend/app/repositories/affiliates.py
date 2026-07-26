"""Affiliate profile repository.

Loads anonymized affiliate data from a CSV file and provides lookup by
document_number (SERIE). The CSV is expected to be a semicolon-delimited
file matching the REAL Colsubsidio dataset schema:

  SERIE;GENERO;RANGO_EDAD;RANGO_SALARIAL;CATEGORIA;
  SEGMENTO_GRUPO_FAMILIAR;SEGMENTO_POBLACIONAL;PIRAMIDE_NUEVA;
  EMPRESA_FOCO;CIUDAD_AFILIADO;HOTELES;PISCILAGO;DROGUERIA;AGENCIAS;
  VIVIENDA

Headers are normalized (accents stripped, uppercased, spaces to
underscores, BOM removed) before being matched against an explicit
column → model field map, so minor header variations still resolve.

`RANGO_SALARIAL` and `RANGO_EDAD` mix two source formats in the real
data (e.g. "Entre 2 y 4 SMLV" and "2-4 SMLV") and can carry mojibake
("a�os") — both are canonicalized by extracting digits only, never
by matching the surrounding text.

Only the first invocation reads the file; subsequent lookups use an
in-memory dictionary. Corrupt rows (missing SERIE or other unparseable
fields) are skipped and reported in `load_errors`; the load continues.
"""

from __future__ import annotations

import csv
import logging
import re
import unicodedata
from pathlib import Path

from app.core.config import settings
from app.models.affiliate import AffiliateProfile

logger = logging.getLogger(__name__)

DEFAULT_AFFILIATE_CSV_PATH = str(
    Path(__file__).resolve().parent.parent / "data" / "afiliados.csv"
)

# Real dataset column (normalized) -> AffiliateProfile field.
HEADER_MAP = {
    "SERIE": "document_number",
    "GENERO": "gender",
    "RANGO_EDAD": "age_range",
    "RANGO_SALARIAL": "salary_range",
    "CATEGORIA": "category",
    "SEGMENTO_GRUPO_FAMILIAR": "household_segment",
    "SEGMENTO_POBLACIONAL": "population_segment",
    "PIRAMIDE_NUEVA": "pyramid",
    "EMPRESA_FOCO": "empresa_foco",
    "CIUDAD_AFILIADO": "city",
    "HOTELES": "uses_hoteles",
    "PISCILAGO": "uses_piscilago",
    "DROGUERIA": "uses_drogueria",
    "AGENCIAS": "uses_agencias",
    "VIVIENDA": "uses_vivienda",
}

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")

# CSV encodings tried in order; the real files ship as utf-8-sig, but
# some exports are latin-1.
_ENCODINGS = ("utf-8-sig", "latin-1")


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def _normalize_header(name: str) -> str:
    """NFKD-strip accents, drop BOM, uppercase, spaces -> underscores."""
    cleaned = name.replace("﻿", "").strip()
    cleaned = _strip_accents(cleaned)
    return cleaned.upper().replace(" ", "_")


def _clean(value: str | None) -> str | None:
    """Trim a raw string field; empty becomes None."""
    if value is None:
        return None
    text = value.strip()
    return text or None


def _parse_mark(value: str | None) -> bool | None:
    """SI -> True, NO -> False, anything else (incl. empty) -> None."""
    if value is None:
        return None
    text = value.strip().upper()
    if text == "SI":
        return True
    if text == "NO":
        return False
    return None


def _normalize_range(value: str | None, suffix: str = "") -> str | None:
    """Canonicalize a range by digits only — immune to mojibake.

    Two numbers found -> "<a>-<b>"; an open-ended signal ("mas de"/
    "más de", ">") or a single trailing number -> "<n>+"; no digits or
    empty input -> None. `suffix` (e.g. "SMLV") is appended when given.
    """
    if not value:
        return None
    text = value.strip()
    if not text:
        return None

    numbers = _NUMBER_RE.findall(text)
    if not numbers:
        return None

    normalized_text = _strip_accents(text).lower()
    open_ended = (
        "mas de" in normalized_text or ">" in text or len(numbers) == 1
    )

    if len(numbers) >= 2 and not open_ended:
        result = f"{numbers[0]}-{numbers[1]}"
    else:
        result = f"{numbers[-1]}+"

    return f"{result} {suffix}".strip() if suffix else result


class AffiliateRepository:
    """Repository backed by an in-memory dict built from CSV."""

    def __init__(self, csv_path: str | None = None) -> None:
        self._csv_path = (
            csv_path or settings.affiliate_csv_path or DEFAULT_AFFILIATE_CSV_PATH
        )
        self._profiles: dict[str, AffiliateProfile] | None = None
        self.load_errors: list[str] = []

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
        """
        records, errors = self._parse_csv(path)
        self._profiles = records
        self.load_errors = errors
        return len(records)

    # -- internals ------------------------------------------------------------

    def _load(self) -> tuple[dict[str, AffiliateProfile], list[str]]:
        """Lazy-load CSV on first call."""
        if self._profiles is not None:
            return self._profiles, self.load_errors
        records, errors = self._parse_csv(self._csv_path)
        self._profiles = records
        self.load_errors = errors
        return records, errors

    def _read_rows(
        self, path: str, encoding: str
    ) -> list[tuple[int, dict[str, str]]]:
        """Read the CSV once, remapping headers to model field names."""
        with open(path, newline="", encoding=encoding) as f:
            reader = csv.DictReader(f, delimiter=";")
            field_map = {
                original: HEADER_MAP.get(_normalize_header(original))
                for original in (reader.fieldnames or [])
            }
            rows: list[tuple[int, dict[str, str]]] = []
            for row_num, row in enumerate(reader, start=2):
                mapped: dict[str, str] = {}
                for original, value in row.items():
                    field = field_map.get(original)
                    if field:
                        mapped[field] = value
                rows.append((row_num, mapped))
            return rows

    def _parse_csv(
        self, path: str
    ) -> tuple[dict[str, AffiliateProfile], list[str]]:
        rows: list[tuple[int, dict[str, str]]] = []
        for encoding in _ENCODINGS:
            try:
                rows = self._read_rows(path, encoding)
                break
            except FileNotFoundError:
                return {}, []  # Graceful fallback — repository returns empty
            except UnicodeDecodeError:
                continue
        else:
            return {}, []

        profiles: dict[str, AffiliateProfile] = {}
        errors: list[str] = []

        for row_num, row in rows:
            serie = (row.get("document_number") or "").strip()
            if not serie:
                errors.append(f"fila {row_num}: falta SERIE")
                continue
            try:
                profiles[serie] = self._row_to_profile(serie, row)
            except (ValueError, TypeError) as exc:
                errors.append(f"fila {row_num}: {exc}")

        if errors:
            logger.warning(
                "carga de afiliados completada con %d error(es)", len(errors)
            )

        return profiles, errors

    @staticmethod
    def _row_to_profile(serie: str, row: dict[str, str]) -> AffiliateProfile:
        city = _clean(row.get("city"))
        return AffiliateProfile(
            document_number=serie,
            age_range=_normalize_range(row.get("age_range")) or "",
            city=city,
            property_type=None,  # not available in the real dataset
            zone="urban" if city else None,
            household_segment=_clean(row.get("household_segment")),
            population_segment=_clean(row.get("population_segment")),
            salary_range=_normalize_range(row.get("salary_range"), suffix="SMLV"),
            gender=_clean(row.get("gender")),
            category=_clean(row.get("category")),
            pyramid=_clean(row.get("pyramid")),
            empresa_foco=_clean(row.get("empresa_foco")),
            uses_hoteles=_parse_mark(row.get("uses_hoteles")),
            uses_piscilago=_parse_mark(row.get("uses_piscilago")),
            uses_drogueria=_parse_mark(row.get("uses_drogueria")),
            uses_agencias=_parse_mark(row.get("uses_agencias")),
            uses_vivienda=_parse_mark(row.get("uses_vivienda")),
        )
