"""Punto de entrada de la aplicación FastAPI."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.conversations import router as conversations_router
from app.api.routes.handoff import router as handoff_router
from app.api.routes.health import router as health_router
from app.api.routes.integrations import router as integrations_router
from app.api.routes.webhooks import router as webhooks_router
from app.core.config import settings
from app.repositories.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Crea las tablas de persistencia al arrancar (sin Alembic, ver `app.repositories.db`)."""
    init_db()
    yield


app = FastAPI(title="Reto Innovación API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(health_router)
api_v1.include_router(integrations_router)
api_v1.include_router(conversations_router)
api_v1.include_router(webhooks_router)
api_v1.include_router(handoff_router)
app.include_router(api_v1)
