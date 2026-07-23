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

## Arquitectura de capas

```
app/
├── main.py          # entrypoint FastAPI
├── core/            # configuración (pydantic-settings)
├── api/routes/      # routers HTTP
├── services/        # lógica de negocio
├── repositories/    # acceso a datos
├── models/          # modelos (SQLModel futuro)
├── schemas/         # DTOs Pydantic
└── helpers/         # utilidades transversales
```

Regla de dependencias: `api → services → repositories → models` — ninguna capa se salta la intermedia.
