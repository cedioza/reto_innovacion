"""Adaptadores de canal (WhatsApp, Telegram, ...).

Cada canal vive en su propio módulo bajo `app.services.channels` y traduce
el formato particular del proveedor hacia/desde el contrato genérico
definido en `app.services.channels.base` (ver ese módulo para el detalle).
Este paquete no expone nada por sí mismo: cada adaptador se importa
directamente desde su submódulo (p. ej. `app.services.channels.base`).
"""
