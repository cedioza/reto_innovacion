"""Check activo de conectividad con Postgres (Dokploy u otro).

Abre una conexión real con `psycopg` y ejecuta `SELECT 1` para confirmar que
`DATABASE_URL` funciona de punta a punta. Nunca lanza excepción: cualquier
fallo se traduce en un `IntegrationCheckResult` con `ok=False`. El mensaje de
error nunca incluye la URL cruda (que puede llevar credenciales).
"""

import time

import psycopg

from app.schemas.health import IntegrationCheckResult


def _normalize_dsn(database_url: str) -> str:
    """Convierte el esquema SQLAlchemy (`postgresql+psycopg://`) al esperado por psycopg."""
    if database_url.startswith("postgresql+psycopg://"):
        return "postgresql://" + database_url[len("postgresql+psycopg://") :]
    return database_url


def check() -> IntegrationCheckResult:
    """Ejecuta `SELECT 1` contra `DATABASE_URL` y devuelve el resultado."""
    from app.core.config import settings

    if not settings.database_url:
        return IntegrationCheckResult(
            service="postgres",
            ok=False,
            detail="no configurado: falta DATABASE_URL",
        )

    dsn = _normalize_dsn(settings.database_url)

    start = time.perf_counter()
    try:
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                row = cur.fetchone()

                if row is None or row[0] != 1:
                    latency_ms = int((time.perf_counter() - start) * 1000)
                    return IntegrationCheckResult(
                        service="postgres",
                        ok=False,
                        latency_ms=latency_ms,
                        detail="SELECT 1 no devolvió el valor esperado",
                    )

                server_version = None
                try:
                    cur.execute("SHOW server_version")
                    version_row = cur.fetchone()
                    if version_row is not None:
                        server_version = version_row[0]
                except psycopg.Error:
                    server_version = None

        latency_ms = int((time.perf_counter() - start) * 1000)
        detail = "SELECT 1 ok"
        if server_version:
            detail = f"SELECT 1 ok (postgres {server_version})"

        return IntegrationCheckResult(
            service="postgres",
            ok=True,
            latency_ms=latency_ms,
            detail=detail,
        )
    except (psycopg.Error, OSError) as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        message = str(exc).splitlines()[0] if str(exc) else ""
        excerpt = message[:200]
        return IntegrationCheckResult(
            service="postgres",
            ok=False,
            latency_ms=latency_ms,
            detail=f"{type(exc).__name__}: {excerpt}",
        )
