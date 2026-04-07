from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..schemas.alert import AlertCreate, AlertRoutingResponse, AlertsListResponse
from ..services import alerts_service

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.post("", status_code=200, response_model=AlertRoutingResponse)
async def submit_alert(
    body: AlertCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await alerts_service.route_alert(db, body)


@router.get("/{alert_id}", status_code=200, response_model=AlertRoutingResponse)
async def get_alert(
    alert_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    response = await alerts_service.get_alert_response(db, alert_id)
    if response is None:
        raise HTTPException(status_code=404, detail={"error": "alert not found"})
    return response


@router.get("", status_code=200, response_model=AlertsListResponse)
async def list_alerts(
    db: Annotated[AsyncSession, Depends(get_db)],
    service: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    routed: bool | None = Query(default=None),
    suppressed: bool | None = Query(default=None),
):
    result = await alerts_service.list_alert_responses(db, service, severity, routed, suppressed)
    if result.total == 0:
        raise HTTPException(status_code=404, detail={"error": "alert not found"})
    return result
