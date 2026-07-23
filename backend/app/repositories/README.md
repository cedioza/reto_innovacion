# repositories/

Acceso a datos (consultas, persistencia). Solo los `services/` llaman a los repositorios; los repositorios trabajan sobre `models/`.

Regla de dependencias: `api → services → repositories → models` — ninguna capa se salta la intermedia.
