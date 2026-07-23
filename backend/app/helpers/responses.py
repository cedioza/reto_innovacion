"""Helpers para construir respuestas JSON con formato estándar."""

from typing import Any


def success_response(data: Any = None, message: str = "ok") -> dict[str, Any]:
    """Envuelve datos en el formato estándar de respuesta exitosa."""
    return {"status": "success", "message": message, "data": data}


def error_response(message: str, details: Any = None) -> dict[str, Any]:
    """Envuelve un error en el formato estándar de respuesta fallida."""
    return {"status": "error", "message": message, "details": details}
