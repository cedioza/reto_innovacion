"""Affiliate profile repository.

Fuente primaria: la tabla `afiliados` (ver `app.models.affiliate_record`),
indexada por SERIE. El CSV/xlsx descrito abajo queda como fallback para
desarrollo (cuando la tabla no existe, está vacía, o la conexión a la BD
falla) y también como parser de carga inicial hacia esa tabla.

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

from sqlalchemy import func
from sqlmodel import Session, select

from app.core.config import settings
from app.models.affiliate import AffiliateProfile
from app.models.affiliate_record import AffiliateRecord
from app.repositories import db

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

    def __init__(self, csv_path: str | None = None, engine=None) -> None:
        self._csv_path = (
            csv_path or settings.affiliate_csv_path or DEFAULT_AFFILIATE_CSV_PATH
        )
        self._engine = engine
        self._profiles: dict[str, AffiliateProfile] | None = None
        self.load_errors: list[str] = []
        self._db_cache: dict[str, AffiliateProfile] = {}
        self._csv_fallback_logged = False

    # -- public API -----------------------------------------------------------

    def find_by_document(self, document_number: str) -> AffiliateProfile | None:
        cached = self._db_cache.get(document_number)
        if cached is not None:
            return cached

        from_db = self._db_lookup(document_number)
        if from_db is not None:
            return from_db

        if self._db_has_rows():
            return None

        self._log_csv_fallback()
        return self._load()[0].get(document_number)

    def exists(self, document_number: str) -> bool:
        if document_number in self._db_cache:
            return True

        if self._db_lookup(document_number) is not None:
            return True

        if self._db_has_rows():
            return False

        self._log_csv_fallback()
        return document_number in self._load()[0]

    def count(self) -> int:
        if self._db_has_rows():
            try:
                with Session(self._resolve_engine()) as session:
                    statement = select(func.count()).select_from(AffiliateRecord)
                    return session.exec(statement).one()
            except Exception:  # noqa: BLE001 - never let a bad DB raise
                pass

        self._log_csv_fallback()
        return len(self._load()[0])

    def count_by_filters(self, filters: dict) -> int:
        """Count `afiliados` rows matching `filters` (cohort queries).

        Each filter is a `column == valor` (scalar) or `column.in_(valor)`
        (list/tuple/set) clause, ANDed together. No BD/tabla/error -> 0,
        same benign fallback as the rest of the DB path.
        """
        try:
            with Session(self._resolve_engine()) as session:
                statement = select(func.count()).select_from(AffiliateRecord)
                statement = self._apply_filters(statement, filters)
                return session.exec(statement).one()
        except Exception:  # noqa: BLE001 - never let a bad DB raise
            return 0

    def sample_by_filters(
        self, filters: dict, limit: int = 5
    ) -> list[AffiliateRecord]:
        """Sample up to `limit` `afiliados` rows matching `filters`.

        Same filter semantics as `count_by_filters`. No BD/tabla/error -> [].
        """
        try:
            with Session(self._resolve_engine()) as session:
                statement = select(AffiliateRecord)
                statement = self._apply_filters(statement, filters)
                statement = statement.limit(limit)
                return list(session.exec(statement).all())
        except Exception:  # noqa: BLE001 - never let a bad DB raise
            return []

    @staticmethod
    def _apply_filters(statement, filters: dict):
        """AND together one WHERE clause per filter (list -> IN, scalar -> ==)."""
        for field, value in filters.items():
            column = getattr(AffiliateRecord, field)
            if isinstance(value, (list, tuple, set)):
                statement = statement.where(column.in_(value))
            else:
                statement = statement.where(column == value)
        return statement

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

    def parsed_profiles(self) -> dict[str, AffiliateProfile]:
        """Devuelve los perfiles ya parseados desde CSV/xlsx (SERIE -> perfil).

        Accesor público mínimo para consumidores que necesitan iterar todos
        los perfiles cargados (p. ej. `app.scripts.cargar_afiliados`) sin
        tocar el diccionario interno `_profiles`. Si no se ha llamado antes
        a `load_from_csv`, dispara la carga perezosa desde `self._csv_path`.
        """
        return self._load()[0]

    # -- internals: DB path -----------------------------------------------------

    def _resolve_engine(self):
        return self._engine or db.get_engine()

    def _log_csv_fallback(self) -> None:
        if not self._csv_fallback_logged:
            logger.info(
                "tabla 'afiliados' no disponible o sin datos; usando fallback CSV/xlsx"
            )
            self._csv_fallback_logged = True

    def _db_has_rows(self) -> bool:
        try:
            with Session(self._resolve_engine()) as session:
                return session.exec(select(AffiliateRecord).limit(1)).first() is not None
        except Exception:  # noqa: BLE001 - never let a bad DB raise
            return False

    def _db_lookup(self, document_number: str) -> AffiliateProfile | None:
        try:
            with Session(self._resolve_engine()) as session:
                record = session.get(AffiliateRecord, document_number)
        except Exception:  # noqa: BLE001 - never let a bad DB raise
            return None

        if record is None:
            return None

        profile = self._record_to_profile(record)
        self._db_cache[document_number] = profile
        return profile

    @staticmethod
    def record_to_profile(record: AffiliateRecord) -> AffiliateProfile:
        """Accesor público: convierte un `AffiliateRecord` en `AffiliateProfile`.

        Delegado mínimo sobre `_record_to_profile` para que consumidores
        externos (p. ej. `app.scripts.curar_series`) no tengan que llamar un
        método "privado" del repositorio.
        """
        return AffiliateRepository._record_to_profile(record)

    @staticmethod
    def _record_to_profile(record: AffiliateRecord) -> AffiliateProfile:
        return AffiliateProfile(
            document_number=record.serie,
            age_range=record.age_range,
            city=record.city,
            property_type=record.sint_tipo_vivienda,
            zone="urban" if record.city else None,
            household_segment=record.household_segment,
            population_segment=record.population_segment,
            salary_range=record.salary_range,
            gender=record.gender,
            category=record.category,
            pyramid=record.pyramid,
            empresa_foco=record.empresa_foco,
            uses_hoteles=record.uses_hoteles,
            uses_piscilago=record.uses_piscilago,
            uses_drogueria=record.uses_drogueria,
            uses_agencias=record.uses_agencias,
            uses_vivienda=record.uses_vivienda,
            has_children=record.sint_tiene_hijos,
            has_vehicle=record.sint_tiene_vehiculo,
            has_credit=record.sint_tiene_credito,
        )

    # -- internals: CSV/xlsx path ------------------------------------------------

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

    def _read_xlsx_rows(
        self, path: str
    ) -> tuple[list[tuple[int, dict[str, str]]] | None, str | None]:
        """Read an xlsx file, remapping headers to model field names.

        Returns (rows, None) on success, (None, None) when the file does
        not exist (silent, mirrors the CSV FileNotFoundError fallback) and
        (None, error_message) when the file exists but cannot be parsed
        as a workbook (corrupt / not a real xlsx).
        """
        import openpyxl  # local import: only needed on the xlsx branch

        try:
            workbook = openpyxl.load_workbook(
                path, read_only=True, data_only=True
            )
        except FileNotFoundError:
            return None, None
        except Exception as exc:  # noqa: BLE001 - never let a bad file raise
            return None, f"no se pudo leer el archivo xlsx: {exc}"

        try:
            sheet = workbook.active
            rows_iter = sheet.iter_rows(values_only=True)
            try:
                header = next(rows_iter)
            except StopIteration:
                return [], None

            field_map = {
                original: HEADER_MAP.get(_normalize_header(str(original)))
                for original in header
                if original is not None
            }

            rows: list[tuple[int, dict[str, str]]] = []
            for row_num, values in enumerate(rows_iter, start=2):
                mapped: dict[str, str] = {}
                for original, value in zip(header, values):
                    field = field_map.get(original)
                    if not field:
                        continue
                    if value is None:
                        mapped[field] = ""
                    elif isinstance(value, str):
                        mapped[field] = value
                    else:
                        mapped[field] = str(value)
                rows.append((row_num, mapped))
            return rows, None
        except Exception as exc:  # noqa: BLE001 - never let a bad file raise
            return None, f"no se pudo leer el archivo xlsx: {exc}"
        finally:
            workbook.close()  # read_only keeps the file open otherwise

    def _rows_to_profiles(
        self, rows: list[tuple[int, dict[str, str]]]
    ) -> tuple[dict[str, AffiliateProfile], list[str]]:
        """Shared mapping/normalization path for both CSV and xlsx rows."""
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

    def _parse_csv(
        self, path: str
    ) -> tuple[dict[str, AffiliateProfile], list[str]]:
        if path.lower().endswith(".xlsx"):
            rows, read_error = self._read_xlsx_rows(path)
            if rows is None:
                return {}, [read_error] if read_error else []
            return self._rows_to_profiles(rows)

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

        return self._rows_to_profiles(rows)

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
