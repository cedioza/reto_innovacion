"""RUNT simulado: consulta de vehículo por placa (plan B5, Fase 2).

**Esto es una simulación.** En producción, `consultar_vehiculo` llamaría al
RUNT (Registro Único Nacional de Tránsito) y/o Fasecolda reales para resolver
marca, línea, modelo (año), tipo de vehículo, cilindraje e historial a partir
de la placa. Aquí entra el RUNT/Fasecolda real en producción; esta deuda
técnica queda documentada explícitamente — misma filosofía que la
aseguradora simulada del handoff (`app.services.handoff`): un catálogo fijo
de vehículos demo más un fallback determinista, nunca una llamada de red.

``PLACAS_DEMO`` es público y deliberado: la demo (y sus tests) necesitan
poder citar una placa conocida (p. ej. ``XYZ987`` → Chevrolet Spark 2020) sin
depender de que el fallback determinista caiga en un bucket concreto.

``consultar_vehiculo(placa)`` normaliza la placa (mayúsculas, solo caracteres
alfanuméricos) y:

1. Si la placa normalizada está en ``PLACAS_DEMO``, devuelve ese vehículo.
2. Si no, cae a un fallback determinista: un hash estable de la placa (suma
   de los códigos ASCII de sus caracteres — **no** el `hash()` builtin de
   Python, que varía entre procesos por el *hash randomization* de
   `str`) selecciona un vehículo de una lista fija de vehículos verosímiles.
   La misma placa desconocida siempre resuelve al mismo vehículo.
3. Si la placa está vacía o no tiene ningún caracter alfanumérico, devuelve
   un dict de error controlado (``{"error": ..., "detail": ...}``) — nunca
   lanza excepción.

Cada vehículo resuelto (demo o fallback) trae siempre las mismas 8 claves:
``placa``, ``marca``, ``linea``, ``modelo`` (int, año), ``tipo`` (``"auto"``
| ``"moto"``), ``cilindraje``, ``historial`` y ``fuente``
(``"RUNT simulado"``).
"""

from __future__ import annotations

import re
from typing import Any

_ALFANUMERICO_RE = re.compile(r"[^A-Z0-9]")

FUENTE = "RUNT simulado"


def _vehiculo(
    *,
    placa: str,
    marca: str,
    linea: str,
    modelo: int,
    tipo: str,
    cilindraje: int,
    historial: str,
) -> dict[str, Any]:
    return {
        "placa": placa,
        "marca": marca,
        "linea": linea,
        "modelo": modelo,
        "tipo": tipo,
        "cilindraje": cilindraje,
        "historial": historial,
        "fuente": FUENTE,
    }


# Catálogo demo: placas conocidas que la demo puede citar de memoria.
# Claves ya normalizadas (mayúsculas, sin guiones/espacios).
PLACAS_DEMO: dict[str, dict[str, Any]] = {
    "XYZ987": {
        "marca": "Chevrolet",
        "linea": "Spark",
        "modelo": 2020,
        "tipo": "auto",
        "cilindraje": 1200,
        "historial": "limpio",
    },
    "ABC123": {
        "marca": "Renault",
        "linea": "Logan",
        "modelo": 2019,
        "tipo": "auto",
        "cilindraje": 1600,
        "historial": "limpio",
    },
    "JKL456": {
        "marca": "Mazda",
        "linea": "3",
        "modelo": 2021,
        "tipo": "auto",
        "cilindraje": 2000,
        "historial": "limpio",
    },
    "QRS789": {
        "marca": "Toyota",
        "linea": "Corolla",
        "modelo": 2018,
        "tipo": "auto",
        "cilindraje": 1800,
        "historial": "un siniestro menor",
    },
    "MNO321": {
        "marca": "Ford",
        "linea": "Escape",
        "modelo": 2017,
        "tipo": "auto",
        "cilindraje": 2500,
        "historial": "limpio",
    },
    "TUV654": {
        "marca": "Yamaha",
        "linea": "FZ",
        "modelo": 2022,
        "tipo": "moto",
        "cilindraje": 150,
        "historial": "limpio",
    },
    "GHI987": {
        "marca": "Honda",
        "linea": "CB160",
        "modelo": 2021,
        "tipo": "moto",
        "cilindraje": 160,
        "historial": "limpio",
    },
    "DEF852": {
        "marca": "Volkswagen",
        "linea": "Gol",
        "modelo": 2016,
        "tipo": "auto",
        "cilindraje": 1400,
        "historial": "un siniestro menor",
    },
}


# Lista fija de vehículos verosímiles usada por el fallback determinista para
# placas que no están en el catálogo demo.
_FALLBACK_VEHICULOS: list[dict[str, Any]] = [
    {
        "marca": "Chevrolet",
        "linea": "Onix",
        "modelo": 2019,
        "tipo": "auto",
        "cilindraje": 1400,
        "historial": "limpio",
    },
    {
        "marca": "Renault",
        "linea": "Sandero",
        "modelo": 2020,
        "tipo": "auto",
        "cilindraje": 1600,
        "historial": "limpio",
    },
    {
        "marca": "Nissan",
        "linea": "Versa",
        "modelo": 2018,
        "tipo": "auto",
        "cilindraje": 1600,
        "historial": "un siniestro menor",
    },
    {
        "marca": "Kia",
        "linea": "Picanto",
        "modelo": 2021,
        "tipo": "auto",
        "cilindraje": 1200,
        "historial": "limpio",
    },
    {
        "marca": "Suzuki",
        "linea": "AKT NKD",
        "modelo": 2020,
        "tipo": "moto",
        "cilindraje": 125,
        "historial": "limpio",
    },
    {
        "marca": "Bajaj",
        "linea": "Pulsar",
        "modelo": 2019,
        "tipo": "moto",
        "cilindraje": 200,
        "historial": "un siniestro menor",
    },
]


def _normalizar(placa: str) -> str:
    return _ALFANUMERICO_RE.sub("", (placa or "").upper())


def _placa_invalida_error(placa: str) -> dict[str, Any]:
    return {
        "error": "placa inválida",
        "detail": f"'{placa}' no tiene caracteres alfanuméricos válidos.",
    }


def _hash_estable(placa_normalizada: str) -> int:
    """Hash estable entre procesos (no usa `hash()` builtin, que varía por
    la aleatorización de hash de `str` en Python)."""
    return sum(ord(caracter) for caracter in placa_normalizada)


def consultar_vehiculo(placa: str) -> dict[str, Any]:
    """Resuelve un vehículo simulado a partir de una placa.

    Nunca lanza excepción: una placa vacía o sin caracteres alfanuméricos
    devuelve un dict de error controlado (`{"error": ..., "detail": ...}`).
    """
    placa_normalizada = _normalizar(placa)
    if not placa_normalizada:
        return _placa_invalida_error(placa)

    demo = PLACAS_DEMO.get(placa_normalizada)
    if demo is not None:
        return _vehiculo(placa=placa_normalizada, **demo)

    indice = _hash_estable(placa_normalizada) % len(_FALLBACK_VEHICULOS)
    fallback = _FALLBACK_VEHICULOS[indice]
    return _vehiculo(placa=placa_normalizada, **fallback)
