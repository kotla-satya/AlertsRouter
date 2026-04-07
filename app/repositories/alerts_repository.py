from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.alert import Alert
from ..models.route_suppression import RouteSuppression


async def upsert_alert(db: AsyncSession, data: dict) -> None:
    result = await db.execute(select(Alert).where(Alert.id == data["id"]))
    existing = result.scalar_one_or_none()
    if existing:
        for key, value in data.items():
            setattr(existing, key, value)
    else:
        db.add(Alert(**data))
    await db.commit()


async def update_routing_result(
    db: AsyncSession,
    alert_id: str,
    routing_result: dict,
    suppressed: bool,
    is_routed: bool,
) -> None:
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one()
    alert.routing_result = routing_result
    alert.suppressed = suppressed
    alert.is_routed = is_routed
    await db.commit()


async def get_alert_by_id(db: AsyncSession, alert_id: str) -> Alert | None:
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    return result.scalar_one_or_none()


async def list_alerts(
    db: AsyncSession,
    service: str | None,
    severity: str | None,
    routed: bool | None,
    suppressed: bool | None,
) -> list[Alert]:
    stmt = select(Alert)
    if service is not None:
        stmt = stmt.where(Alert.service == service)
    if severity is not None:
        stmt = stmt.where(Alert.severity == severity)
    if routed is not None:
        stmt = stmt.where(Alert.is_routed == routed)
    if suppressed is not None:
        stmt = stmt.where(Alert.suppressed == suppressed)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_alerts(
    db: AsyncSession,
    is_routed: bool | None = None,
    suppressed: bool | None = None,
) -> int:
    stmt = select(func.count()).select_from(Alert)
    if is_routed is not None:
        stmt = stmt.where(Alert.is_routed == is_routed)
    if suppressed is not None:
        stmt = stmt.where(Alert.suppressed == suppressed)
    result = await db.execute(stmt)
    return result.scalar_one()


async def count_by_severity(db: AsyncSession) -> dict[str, int]:
    result = await db.execute(select(Alert.severity, func.count()).group_by(Alert.severity))
    return {severity: count for severity, count in result.all()}


async def count_by_service(db: AsyncSession) -> dict[str, int]:
    result = await db.execute(select(Alert.service, func.count()).group_by(Alert.service))
    return {service: count for service, count in result.all()}


async def get_suppression(db: AsyncSession, route_id: str, service: str) -> RouteSuppression | None:
    result = await db.execute(
        select(RouteSuppression).where(
            RouteSuppression.route_id == route_id,
            RouteSuppression.service == service,
        )
    )
    return result.scalar_one_or_none()


async def upsert_suppression(
    db: AsyncSession, route_id: str, service: str, last_routed_at: datetime
) -> None:
    existing = await get_suppression(db, route_id, service)
    if existing:
        existing.last_routed_at = last_routed_at
    else:
        db.add(RouteSuppression(route_id=route_id, service=service, last_routed_at=last_routed_at))
    await db.commit()
