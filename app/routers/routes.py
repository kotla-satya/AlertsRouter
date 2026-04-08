from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..schemas.routing_config import RoutingConfigCreate, RoutingConfigResponse, RouteUpsertResponse
from ..services import routes_service

router = APIRouter(prefix="/routes", tags=["routes"])


@router.post("", status_code=201, response_model=RouteUpsertResponse)
async def create_or_update_route(
    body: RoutingConfigCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Create a new routing config or replace an existing one by ID.

    Matches alerts by severity, service (glob), group, and/or labels.
    The highest-priority matching route wins when multiple rules apply.
    Set `suppression_window_seconds` to silence duplicate alerts from the same
    service within the given window. Set `active_hours` to restrict the route
    to a time-of-day window in any IANA timezone.

    Returns `{"id": ..., "created": true}` for new routes and `{"id": ..., "created": false}`
    for updates.
    """
    return await routes_service.upsert_route(db, body)


@router.get("", response_model=list[RoutingConfigResponse])
async def get_routes(
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Return all routing configs ordered by priority descending (highest first).
    """
    return await routes_service.list_routes(db)


@router.delete("/{route_id}", status_code=200)
async def delete_route(
    route_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Delete a routing config by ID.

    Returns `{"id": ..., "deleted": true}` on success.
    Returns `{"error": "route not found"}` with 404 if the ID does not exist.
    """
    await routes_service.delete_route(db, route_id)
    return {"id": route_id, "deleted": True}
