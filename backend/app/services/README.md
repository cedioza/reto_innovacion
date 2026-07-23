# services/

Lógica de negocio de la aplicación. Los routers de `api/` llaman a estos servicios, y estos a su vez usan `repositories/` para acceder a datos.

Regla de dependencias: `api → services → repositories → models` — ninguna capa se salta la intermedia.
