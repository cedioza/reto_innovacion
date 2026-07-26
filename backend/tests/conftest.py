"""Configuración compartida de la suite de tests del backend.

El engine de `app.repositories.db` es un singleton perezoso a nivel de
módulo: si ninguna variable de entorno `DATABASE_URL` está configurada (caso
normal en CI/local sin Postgres), `get_engine()` cae a un archivo SQLite en
`backend/app/data/local.db`. Varios tests instancian `ConversationService`
(o usan el singleton `conversation_service`) sin pasar un engine explícito,
así que terminarían disparando ese fallback y escribiendo en disco durante la
suite.

Este fixture autouse de sesión redirige el engine global a un SQLite
in-memory compartido (`StaticPool`, para que todas las conexiones vean las
mismas tablas) antes de que corra cualquier test, y crea el esquema con
`init_db`. Así la suite completa nunca toca el filesystem.
"""

from __future__ import annotations

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

from app.repositories import db as db_module


@pytest.fixture(scope="session", autouse=True)
def _in_memory_db_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db_module.init_db(engine)
    db_module._engine = engine
    yield engine
