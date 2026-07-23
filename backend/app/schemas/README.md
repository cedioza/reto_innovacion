# schemas/

DTOs de Pydantic: cuerpos de request y modelos de response que expone la API. Los usan `api/` y `services/` para validar entrada/salida; no contienen lógica de persistencia.

Regla de dependencias: `api → services → repositories → models` — ninguna capa se salta la intermedia.
