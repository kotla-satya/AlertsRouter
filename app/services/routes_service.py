from fastapi import HTTPException
from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.routing_config import RoutingConfig
from ..repositories import routes_repository
from ..schemas.routing_config import (
    ActiveHours,
    RoutingConfigCondition,
    RoutingConfigCreate,
    RoutingConfigResponse,
    RoutingConfigTarget,
    RouteUpsertResponse,
)

_target_adapter = TypeAdapter(RoutingConfigTarget)


def _to_response(route: RoutingConfig) -> RoutingConfigResponse:
    return RoutingConfigResponse(
        id=route.id,
        conditions=RoutingConfigCondition.model_validate(route.conditions),
        target=_target_adapter.validate_python(route.target),
        priority=route.priority,
        suppression_window_seconds=route.suppression_window_seconds,
        active_hours=ActiveHours.model_validate(route.active_hours) if route.active_hours else None,
    )


async def upsert_route(db: AsyncSession, body: RoutingConfigCreate) -> RouteUpsertResponse:
    #Note: if alerts are created for a route, we don't restrict the update to a route config

    existing = await routes_repository.get_by_id(db, body.id)
    was_created = existing is None

    data = dict(
        id=body.id,
        conditions=body.conditions.model_dump(),
        target=body.target.model_dump(),
        priority=body.priority,
        suppression_window_seconds=body.suppression_window_seconds,
        active_hours=body.active_hours.model_dump() if body.active_hours else None,
    )

    if existing:
        data["version"] = existing.version + 1
        await routes_repository.update_fields(db, existing, data)
    else:
        await routes_repository.add(db, RoutingConfig(**data))

    return RouteUpsertResponse(id=body.id, created=was_created)


async def list_routes(db: AsyncSession) -> list[RoutingConfigResponse]:
    routes = await routes_repository.list_all(db)
    return [_to_response(r) for r in routes]


async def delete_route(db: AsyncSession, route_id: str) -> None:
    route = await routes_repository.get_by_id(db, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="route not found")
    await routes_repository.delete(db, route)
