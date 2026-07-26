"""Matriz de Perfilamiento — fricción cero (Reto Seguros, plan B5).

La Matriz de Perfilamiento (fuente: vault de negocio) define, por categoría
de seguro, el trío `dato → vía afiliado (preguntar | deducido base | deducido
API) → vía no afiliado`. El principio rector es **fricción cero**: a un
afiliado no se le pregunta lo que la base de Colsubsidio (SSO/PILA) ya sabe
de él; a un prospecto (no afiliado, o afiliado sin esos datos en base) todo
lo "deducible" se convierte en pregunta, sin romper el flujo conversacional.

``MATRIX`` es la única fuente de verdad de este módulo: para cada categoría
del catálogo (``hogar``, ``vida``, ``accidentes``, ``movilidad``, ``credito``)
declara una lista ordenada de campos con:

- ``campo``: nombre corto y estable del dato (el que usa el LLM y los tests).
- ``pregunta_sugerida``: cómo pedirlo con naturalidad si toca preguntarlo.
- ``fuente_afiliado``: de dónde saldría el dato **para un afiliado** sin
  preguntarlo — ``"base"`` (Colsubsidio, SSO/PILA), ``"api_simulada"``
  (una integración externa simulada, p. ej. RUNT/Fasecolda para vehículos —
  ver Fase 2 del plan B5) o ``"preguntar"`` (no hay vía deducida, siempre se
  pregunta salvo que el cliente ya lo haya declarado en la conversación).
- ``atributo_perfil``: el campo de ``ProfileData`` donde vive el valor
  resuelto, o ``None`` cuando el dato no tiene todavía soporte estructurado
  en el perfil (p. ej. ocupación, ingresos) — en ese caso el dato "vive" en
  la Matriz como texto (para que el bot sepa que no debe preguntarlo a un
  afiliado) pero no se persiste como campo aparte del perfil.

Restricción deliberada (hackathon, ver plan B5): solo entran a la Matriz los
campos que el motor de propensión/cotización realmente usa, que el bot debe
saber que NO debe preguntarle a un afiliado, o que la demo cita — no se
agregan campos "muertos" que la Matriz del vault sí trae (IMC, microchip de
mascota, año de construcción, etc.) pero que ningún flujo real consume.

``campos_pendientes(categoria, profile)`` es la función pura que resuelve,
para un perfil concreto, qué de la Matriz ya se conoce y qué falta:

- Un campo con ``fuente_afiliado == "base"`` se marca conocido (fuente
  legible ``"base Colsubsidio (SSO/PILA)"``) apenas ``profile.source ==
  "base"`` — fricción cero honesta: si el afiliado vino de la base, ese dato
  ya está ahí (con o sin soporte estructurado en ``ProfileData``), así que
  jamás se le pregunta.
- Cualquier otro campo (``"preguntar"`` o ``"api_simulada"`` sin ese atajo)
  se marca conocido si su ``atributo_perfil`` ya tiene un valor en el
  perfil — la fuente legible es ``"declarado"`` (el cliente lo dijo en la
  conversación) o ``"RUNT simulado"`` cuando ``fuente_afiliado ==
  "api_simulada"`` (p. ej. marca/línea/año de un vehículo ya resuelto por
  ``consultar_vehiculo``, Fase 2).
- En cualquier otro caso, el campo queda pendiente con su
  ``pregunta_sugerida``.

Los atributos se leen con ``getattr(profile, atributo_perfil, None)`` para
tolerar perfiles (o versiones futuras de ``ProfileData``) que todavía no
declaren ese atributo explícitamente.
"""

from __future__ import annotations

from typing import Any

MATRIX: dict[str, list[dict[str, Any]]] = {
    "vida": [
        {
            "campo": "edad",
            "pregunta_sugerida": "¿Cuál es tu rango de edad?",
            "fuente_afiliado": "base",
            "atributo_perfil": "age_range",
        },
        {
            "campo": "genero",
            "pregunta_sugerida": "¿Con qué género te identificas?",
            "fuente_afiliado": "base",
            "atributo_perfil": "gender",
        },
        {
            "campo": "ocupacion",
            "pregunta_sugerida": "¿A qué te dedicas actualmente?",
            "fuente_afiliado": "base",
            "atributo_perfil": None,
        },
        {
            "campo": "ingresos",
            "pregunta_sugerida": "¿En qué rango están tus ingresos mensuales?",
            "fuente_afiliado": "base",
            "atributo_perfil": None,
        },
        {
            "campo": "fumador",
            "pregunta_sugerida": "¿Fumas actualmente?",
            "fuente_afiliado": "preguntar",
            "atributo_perfil": None,
        },
        {
            "campo": "deportes_extremos",
            "pregunta_sugerida": "¿Practicas deportes extremos?",
            "fuente_afiliado": "preguntar",
            "atributo_perfil": None,
        },
    ],
    "accidentes": [
        {
            "campo": "edad",
            "pregunta_sugerida": "¿Cuál es tu rango de edad?",
            "fuente_afiliado": "base",
            "atributo_perfil": "age_range",
        },
        {
            "campo": "genero",
            "pregunta_sugerida": "¿Con qué género te identificas?",
            "fuente_afiliado": "base",
            "atributo_perfil": "gender",
        },
        {
            "campo": "ocupacion",
            "pregunta_sugerida": "¿A qué te dedicas actualmente?",
            "fuente_afiliado": "base",
            "atributo_perfil": None,
        },
        {
            "campo": "actividad_riesgo",
            "pregunta_sugerida": (
                "¿Realizas actividades de riesgo (deportes extremos, trabajo "
                "en alturas, etc.)?"
            ),
            "fuente_afiliado": "preguntar",
            "atributo_perfil": None,
        },
    ],
    "movilidad": [
        {
            "campo": "edad",
            "pregunta_sugerida": "¿Cuál es tu rango de edad?",
            "fuente_afiliado": "base",
            "atributo_perfil": "age_range",
        },
        {
            "campo": "ciudad",
            "pregunta_sugerida": "¿En qué ciudad circula el vehículo?",
            "fuente_afiliado": "base",
            "atributo_perfil": None,
        },
        {
            "campo": "placa",
            "pregunta_sugerida": "¿Cuál es la placa de tu vehículo?",
            "fuente_afiliado": "preguntar",
            "atributo_perfil": None,
        },
        {
            "campo": "marca_modelo",
            "pregunta_sugerida": (
                "Se obtiene automáticamente al validar la placa (RUNT "
                "simulado, ver Fase 2) — no se pregunta directamente."
            ),
            "fuente_afiliado": "api_simulada",
            "atributo_perfil": None,
        },
        {
            "campo": "uso_vehiculo",
            "pregunta_sugerida": "¿El vehículo lo usas particular o para trabajo?",
            "fuente_afiliado": "preguntar",
            "atributo_perfil": None,
        },
    ],
    "hogar": [
        {
            "campo": "ciudad",
            "pregunta_sugerida": "¿En qué ciudad está tu vivienda?",
            "fuente_afiliado": "base",
            "atributo_perfil": None,
        },
        {
            "campo": "estrato",
            "pregunta_sugerida": "¿Cuál es el estrato de tu vivienda?",
            "fuente_afiliado": "base",
            "atributo_perfil": "stratum",
        },
        {
            "campo": "tipo_inmueble",
            "pregunta_sugerida": "¿Tu vivienda es casa o apartamento?",
            "fuente_afiliado": "preguntar",
            "atributo_perfil": "property_type",
        },
        {
            "campo": "rol_vivienda",
            "pregunta_sugerida": "¿Vives en tu vivienda como propietario o arrendatario?",
            "fuente_afiliado": "preguntar",
            "atributo_perfil": None,
        },
        {
            "campo": "medidas_seguridad",
            "pregunta_sugerida": (
                "¿Tu vivienda tiene medidas de seguridad como alarma o "
                "cámaras?"
            ),
            "fuente_afiliado": "preguntar",
            "atributo_perfil": None,
        },
    ],
    "credito": [
        {
            "campo": "edad",
            "pregunta_sugerida": "¿Cuál es tu rango de edad?",
            "fuente_afiliado": "base",
            "atributo_perfil": "age_range",
        },
        {
            "campo": "genero",
            "pregunta_sugerida": "¿Con qué género te identificas?",
            "fuente_afiliado": "base",
            "atributo_perfil": "gender",
        },
        {
            "campo": "entidad",
            "pregunta_sugerida": "¿Con qué entidad tienes tu crédito?",
            "fuente_afiliado": "base",
            "atributo_perfil": None,
        },
        {
            "campo": "saldo",
            "pregunta_sugerida": "¿Cuál es el saldo aproximado de tu crédito?",
            "fuente_afiliado": "base",
            "atributo_perfil": None,
        },
    ],
}


def campos_pendientes(categoria: str, profile: Any) -> dict[str, list[dict[str, Any]]]:
    """Resuelve, para `categoria`, qué campos de la Matriz ya se conocen y cuáles faltan.

    Devuelve `{"conocidos": [...], "pendientes": [...]}`:

    - Cada item de `conocidos` trae `{"campo", "valor", "fuente"}` con la
      fuente legible ("base Colsubsidio (SSO/PILA)" / "declarado" / "RUNT
      simulado").
    - Cada item de `pendientes` trae `{"campo", "pregunta_sugerida"}`, en el
      orden declarado en `MATRIX`.

    Lanza `ValueError` si `categoria` no es una de las declaradas en
    `MATRIX`.
    """
    if categoria not in MATRIX:
        raise ValueError(f"categoría desconocida: {categoria!r}")

    conocidos: list[dict[str, Any]] = []
    pendientes: list[dict[str, Any]] = []

    for campo in MATRIX[categoria]:
        atributo = campo["atributo_perfil"]
        valor = getattr(profile, atributo, None) if atributo else None
        fuente_afiliado = campo["fuente_afiliado"]

        if fuente_afiliado == "base" and getattr(profile, "source", None) == "base":
            conocidos.append(
                {
                    "campo": campo["campo"],
                    "valor": valor,
                    "fuente": "base Colsubsidio (SSO/PILA)",
                }
            )
        elif valor is not None:
            fuente = "RUNT simulado" if fuente_afiliado == "api_simulada" else "declarado"
            conocidos.append(
                {"campo": campo["campo"], "valor": valor, "fuente": fuente}
            )
        else:
            pendientes.append(
                {
                    "campo": campo["campo"],
                    "pregunta_sugerida": campo["pregunta_sugerida"],
                }
            )

    return {"conocidos": conocidos, "pendientes": pendientes}
