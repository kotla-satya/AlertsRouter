from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.routing_config import RoutingConfig


async def get_by_id(db: AsyncSession, route_id: str) -> RoutingConfig | None:
    result = await db.execute(select(RoutingConfig).where(RoutingConfig.id == route_id))
    return result.scalar_one_or_none()


async def add(db: AsyncSession, route: RoutingConfig) -> None:
    db.add(route)
    await db.commit()


async def update_fields(db: AsyncSession, route: RoutingConfig, data: dict) -> None:
    for key, value in data.items():
        setattr(route, key, value)
    await db.commit()


async def list_all(db: AsyncSession) -> list[RoutingConfig]:
    result = await db.execute(select(RoutingConfig).order_by(RoutingConfig.priority.desc()))
    return list(result.scalars().all())


async def delete(db: AsyncSession, route: RoutingConfig) -> None:
    await db.delete(route)
    await db.commit()
