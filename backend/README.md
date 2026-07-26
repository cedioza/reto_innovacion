# Backend — FastAPI

API del reto de innovación construida con [FastAPI](https://fastapi.tiangolo.com/).

## Requisitos

- Python 3.12+

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate    # Windows
# source .venv/bin/activate    # Linux / macOS
pip install -e ".[dev]"
copy .env.example .env    # cp en Linux / macOS
```

## Ejecución

```bash
uvicorn app.main:app --reload
```

La API queda disponible en `http://localhost:8000` y la documentación interactiva en `http://localhost:8000/docs`.

## Tests

```bash
pytest
```

## Persistencia (C3)

Las conversaciones (transcripción completa), las solicitudes con consentimiento y
las sesiones de canal (teléfono→conversación) se persisten vía **SQLModel** en las
tablas `conversaciones`, `solicitudes`, `sesiones_canal` y `eventos_procesados`
(esta última deduplica webhooks de YCloud entre reinicios).

- **Motor**: `DATABASE_URL` (ver `.env.example`). Con la variable vacía el backend
  cae a un SQLite local de desarrollo (`app/data/local.db`, ignorado por git).
  Para Postgres local: `docker compose up -d db` desde la raíz del monorepo y
  `DATABASE_URL=postgresql://reto:reto@localhost:5432/reto_innovacion`.
- **Esquema**: `SQLModel.metadata.create_all` en el lifespan de la app — sin
  Alembic, decisión de hackathon (los modelos se crean solos al arrancar).
- **Diseño**: cada registro guarda el documento Pydantic completo en una columna
  JSON (JSONB en Postgres) más columnas indexables (`estado`, `handoff_token`,
  `evidence_hash`); los repositorios conservan el contrato previo, así que
  services y API no cambiaron.
- **Tests**: los repos se prueban contra SQLite in-memory por velocidad/CI (nota
  de compatibilidad en cada módulo de tests); el shape SQL es compatible con
  Postgres.

## Arquitectura de capas

```
app/
├── main.py          # entrypoint FastAPI
├── core/            # configuración (pydantic-settings)
├── api/routes/      # routers HTTP
├── services/        # lógica de negocio
├── repositories/    # acceso a datos
├── models/          # modelos de persistencia (SQLModel)
├── schemas/         # DTOs Pydantic
└── helpers/         # utilidades transversales
```

Regla de dependencias: `api → services → repositories → models` — ninguna capa se salta la intermedia.
