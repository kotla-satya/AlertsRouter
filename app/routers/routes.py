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
    return await routes_service.upsert_route(db, body)


@router.get("", response_model=list[RoutingConfigResponse])
async def get_routes(
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await routes_service.list_routes(db)


@router.delete("/{route_id}", status_code=200)
async def delete_route(
    route_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await routes_service.delete_route(db, route_id)
    return {}
