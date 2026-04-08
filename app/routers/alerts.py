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
    """
    Submit an alert for routing and persist the result.

    The alert is evaluated against all active routing configs. The highest-priority
    matching route becomes `routed_to`. If the primary route has a suppression window
    active for the same service, the alert is suppressed (`suppressed: true`) and no
    new suppression record is written. `matched_routes` lists every route whose
    conditions matched, regardless of suppression.
    """
    return await alerts_service.route_alert(db, body)


@router.get("/{alert_id}", status_code=200, response_model=AlertRoutingResponse)
async def get_alert(
    alert_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Return the routing result for a previously submitted alert.

    Returns `{"error": "alert not found"}` with 404 if the ID does not exist.
    """
    response = await alerts_service.get_alert_response(db, alert_id)
    if response is None:
        raise HTTPException(status_code=404, detail="alert not found")
    return response


@router.get("", status_code=200, response_model=AlertsListResponse)
async def list_alerts(
    db: Annotated[AsyncSession, Depends(get_db)],
    service: str | None = Query(default=None, description="Filter by exact service name"),
    severity: str | None = Query(default=None, description="Filter by severity (`critical`, `warning`, `info`)"),
    routed: bool | None = Query(default=None, description="Filter by whether the alert was dispatched (`true`) or suppressed (`false`)"),
    suppressed: bool | None = Query(default=None, description="Filter by suppression status"),
):
    """
    List alert routing results with optional filters. All filters are optional and combined with AND.

    Returns all matching alerts in a single response — there is no pagination.
    An empty result set returns `{"alerts": [], "total": 0}` with 200.

    Note: `routed=false` matches alerts that were suppressed (matched a route but not dispatched).
    """
    return await alerts_service.list_alert_responses(db, service, severity, routed, suppressed)
