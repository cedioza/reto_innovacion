"""Servicio del perfil enriquecido declarado en conversación (plan A4).

Whitelist de la Matriz de Perfilamiento, sin ontología abierta; el service es
el único punto de validación: valida y normaliza cada campo antes de
delegarlo al `EnrichedProfileRepository`, y resuelve la lectura combinada de
sesión + serie (la sesión pisa a la serie). El campo `nombre` es una
excepción: es solo personalización del trato (saludo), no una señal del
perfil, así que nunca entra al motor de propensión/tarifas.
"""

from __future__ import annotations

from typing import Callable

from sqlalchemy import Engine

from app.models.enriched_field import EnrichedFieldRecord
from app.repositories.enriched_profile import EnrichedProfileRepository


def _validate_hijos(valor: str) -> str:
    try:
        cantidad = int(valor.strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"valor inválido para hijos: {valor!r}") from exc
    if cantidad < 0:
        raise ValueError(f"valor inválido para hijos: {valor!r}")
    return str(cantidad)


def _enum_validator(options: set[str]) -> Callable[[str], str]:
    def _validate(valor: str) -> str:
        normalizado = valor.strip().lower()
        if normalizado not in options:
            raise ValueError(f"valor no permitido: {valor!r}")
        return normalizado

    return _validate


def _validate_ocupacion(valor: str) -> str:
    normalizado = valor.strip()
    if not normalizado:
        raise ValueError("ocupacion no puede estar vacía")
    if len(normalizado) > 80:
        raise ValueError("ocupacion excede el largo máximo (80 caracteres)")
    return normalizado


def _validate_nombre(valor: str) -> str:
    normalizado = valor.strip()
    if not normalizado:
        raise ValueError("nombre no puede estar vacío")
    if len(normalizado) > 60:
        raise ValueError("nombre excede el largo máximo (60 caracteres)")
    if any(ch.isdigit() for ch in normalizado):
        raise ValueError("nombre no puede contener dígitos")
    return normalizado


class EnrichmentService:
    """Dueño del `EnrichedProfileRepository`: valida, normaliza y persiste."""

    ALLOWED_FIELDS: dict[str, Callable[[str], str]] = {
        "hijos": _validate_hijos,
        "mascota": _enum_validator({"perro", "gato", "otro", "ninguna"}),
        "vehiculo": _enum_validator({"si", "no"}),
        "credito": _enum_validator({"si", "no"}),
        "fumador": _enum_validator({"si", "no"}),
        "ocupacion": _validate_ocupacion,
        "tipo_vivienda": _enum_validator({"house", "apartment"}),
        "nombre": _validate_nombre,
    }

    def __init__(self, engine: Engine | None = None) -> None:
        self._repo = EnrichedProfileRepository(engine=engine)

    def record(self, session_id: str, serie: str | None, campo: str, valor: str) -> str:
        validador = self.ALLOWED_FIELDS.get(campo)
        if validador is None:
            raise ValueError(f"campo no permitido: {campo!r}")
        normalizado = validador(valor)
        self._repo.add(session_id, serie, campo, normalizado)
        return normalizado

    def fields_for(self, session_id: str, serie: str | None = None) -> dict[str, str]:
        combinado: dict[str, str] = {}
        if serie:
            combinado.update(self._repo.fields_for_serie(serie))
        combinado.update(self._repo.fields_for_session(session_id))
        return combinado

    def all_fields(self) -> list[EnrichedFieldRecord]:
        """Lista todas las filas EAV (plan G4, Fase 2: vista de clientes).

        Delegación directa al `EnrichedProfileRepository.list_all()` subyacente.
        """
        return self._repo.list_all()
