# models/

Modelos de datos (futuro SQLModel) que representan las tablas / entidades del dominio. Solo `repositories/` los usa directamente para persistencia.

Regla de dependencias: `api → services → repositories → models` — ninguna capa se salta la intermedia.
