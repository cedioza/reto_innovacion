# Backend — Reglas de arquitectura

API FastAPI con arquitectura de capas estricta.

## Regla de dependencias (obligatoria)

```
api → services → repositories → models
```

- Ninguna capa se salta la intermedia: un router NUNCA llama a un repository ni toca models; un service NUNCA ejecuta queries directamente.
- Las dependencias van en una sola dirección: una capa inferior nunca importa de una superior (un repository no importa de services ni de api).
- Cada service es dueño de UN único repository: el suyo. Si necesita datos de otra entidad, los pide al service de esa entidad, nunca a su repository directamente. Un service sí puede componer otros services (patrón orquestador, p. ej. `ConversationService`).

## Qué va en cada capa

- `app/api/routes/` — routers HTTP. Delgados: validan entrada (schemas), llaman a un service y devuelven la respuesta. Sin lógica de negocio.
- `app/services/` — lógica de negocio. Orquestan repositories y helpers. No conocen FastAPI (nada de `Request`, `HTTPException` se lanza aquí solo si es regla de negocio).
- `app/repositories/` — todo acceso a datos. Único lugar que ejecuta queries y conoce la persistencia.
- `app/models/` — modelos de persistencia (SQLModel futuro). Los produce y consume `repositories/`; los services pueden recibirlos y convertirlos a schemas; **nunca** llegan a `api/` ni se exponen en la API.
- `app/schemas/` — DTOs Pydantic de request/response. Los usan `api/` y `services/`; nunca exponer models directamente en la API.
- `app/helpers/` — utilidades transversales puras (formateo, fechas). Sin lógica de negocio, sin acceso a datos; cualquier capa puede usarlas.
- `app/core/` — configuración. Toda variable de entorno se lee vía `Settings` (pydantic-settings) en `core/config.py`; nunca `os.environ` directo en otras capas.

## Convenciones

- Todo endpoint HTTP cuelga de `/api/v1` (el router raíz de `main.py`); los routers declaran su prefijo SIN `/api/v1`.
- Nuevo endpoint = nuevo router en `api/routes/` registrado en `main.py`, con su schema en `schemas/` y su service en `services/`.
- Cada endpoint nuevo lleva al menos un test en `tests/` (patrón: `tests/test_health.py` con `TestClient`).
- Nueva variable de entorno = campo en `Settings` + entrada en `.env.example`.
