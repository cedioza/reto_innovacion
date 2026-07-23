# Backend — FastAPI

API del reto de innovación construida con [FastAPI](https://fastapi.tiangolo.com/).

## Requisitos

- Python 3.11+

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate    # Windows
# source .venv/bin/activate    # Linux / macOS
pip install -r requirements.txt
```

## Ejecución

```bash
uvicorn app.main:app --reload
```

La API queda disponible en `http://localhost:8000` y la documentación interactiva en `http://localhost:8000/docs`.
