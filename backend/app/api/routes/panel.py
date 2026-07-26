"""Panel API router (disparador proactivo).

Thin layer: delegates to ProactiveService and returns the response
validated by CohortsResponse. No business logic here.
"""

from fastapi import APIRouter, HTTPException

from app.schemas.panel import (
    ClienteFicha,
    ClientesResponse,
    CohortsResponse,
    MetricasResponse,
    TriggerRequest,
    TriggerResponse,
)
from app.services.panel_clientes import PanelClientesService
from app.services.panel_metrics import PanelMetricsService
from app.services.proactive import ProactiveService

router = APIRouter(prefix="/panel", tags=["panel"])


@router.get("/cohortes", response_model=CohortsResponse)
async def get_cohortes():
    return ProactiveService().list_cohorts()


@router.get("/metricas", response_model=MetricasResponse)
async def get_metricas():
    return PanelMetricsService().metricas()


@router.post(
    "/cohortes/{cohorte_id}/disparar",
    response_model=TriggerResponse,
    status_code=201,
)
async def disparar_cohorte(cohorte_id: str, body: TriggerRequest):
    try:
        return ProactiveService().trigger(cohorte_id, body.serie)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/clientes", response_model=ClientesResponse)
async def get_clientes(q: str | None = None):
    return PanelClientesService().list_clientes(q)


@router.get("/clientes/{cliente_id}", response_model=ClienteFicha)
async def get_cliente_ficha(cliente_id: str):
    try:
        return PanelClientesService().ficha(cliente_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
