"""Unit tests for routes_service.upsert_route."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import routes_repository
from app.schemas.routing_config import (
    ActiveHours,
    RoutingConfigCondition,
    RoutingConfigCreate,
)
from app.services import routes_service


def _body(**overrides) -> RoutingConfigCreate:
    base = dict(
        id="route-1",
        conditions=RoutingConfigCondition(),
        target={"type": "slack", "channel": "#alerts"},
        priority=10,
        suppression_window_seconds=0,
        active_hours=None,
    )
    return RoutingConfigCreate(**{**base, **overrides})


# ---------------------------------------------------------------------------
# Create (route does not exist)
# ---------------------------------------------------------------------------

async def test_upsert_creates_new_route(db_session: AsyncSession):
    result = await routes_service.upsert_route(db_session, _body())

    assert result.id == "route-1"
    assert result.created is True


async def test_upsert_create_persists_to_db(db_session: AsyncSession):
    await routes_service.upsert_route(db_session, _body())

    stored = await routes_repository.get_by_id(db_session, "route-1")
    assert stored is not None
    assert stored.priority == 10
    assert stored.suppression_window_seconds == 0


async def test_upsert_create_persists_conditions(db_session: AsyncSession):
    cond = RoutingConfigCondition(severity=["critical"], service=["payment-*"])
    await routes_service.upsert_route(db_session, _body(conditions=cond))

    stored = await routes_repository.get_by_id(db_session, "route-1")
    assert stored.conditions["severity"] == ["critical"]
    assert stored.conditions["service"] == ["payment-*"]


async def test_upsert_create_persists_target(db_session: AsyncSession):
    target = {"type": "email", "address": "ops@example.com"}
    await routes_service.upsert_route(db_session, _body(id="route-email", target=target))

    stored = await routes_repository.get_by_id(db_session, "route-email")
    assert stored.target["type"] == "email"
    assert stored.target["address"] == "ops@example.com"


async def test_upsert_create_persists_active_hours(db_session: AsyncSession):
    ah = ActiveHours(start="09:00", end="17:00", timezone="America/New_York")
    await routes_service.upsert_route(db_session, _body(active_hours=ah))

    stored = await routes_repository.get_by_id(db_session, "route-1")
    assert stored.active_hours["start"] == "09:00"
    assert stored.active_hours["end"] == "17:00"
    assert stored.active_hours["timezone"] == "America/New_York"


async def test_upsert_create_version_starts_at_1(db_session: AsyncSession):
    await routes_service.upsert_route(db_session, _body())

    stored = await routes_repository.get_by_id(db_session, "route-1")
    assert stored.version == 1


# ---------------------------------------------------------------------------
# Update (route already exists)
# ---------------------------------------------------------------------------

async def test_upsert_updates_existing_route(db_session: AsyncSession):
    await routes_service.upsert_route(db_session, _body())

    result = await routes_service.upsert_route(db_session, _body(priority=99))

    assert result.id == "route-1"
    assert result.created is False


async def test_upsert_update_persists_changed_fields(db_session: AsyncSession):
    await routes_service.upsert_route(db_session, _body())
    await routes_service.upsert_route(db_session, _body(priority=99, suppression_window_seconds=300))

    stored = await routes_repository.get_by_id(db_session, "route-1")
    assert stored.priority == 99
    assert stored.suppression_window_seconds == 300


async def test_upsert_update_increments_version(db_session: AsyncSession):
    await routes_service.upsert_route(db_session, _body())
    await routes_service.upsert_route(db_session, _body(priority=99))

    stored = await routes_repository.get_by_id(db_session, "route-1")
    assert stored.version == 2


async def test_upsert_multiple_updates_increment_version_each_time(db_session: AsyncSession):
    await routes_service.upsert_route(db_session, _body())
    await routes_service.upsert_route(db_session, _body(priority=20))
    await routes_service.upsert_route(db_session, _body(priority=30))

    stored = await routes_repository.get_by_id(db_session, "route-1")
    assert stored.version == 3


async def test_upsert_update_replaces_conditions(db_session: AsyncSession):
    await routes_service.upsert_route(db_session, _body(conditions=RoutingConfigCondition(severity=["critical"])))
    await routes_service.upsert_route(db_session, _body(conditions=RoutingConfigCondition(severity=["warning"])))

    stored = await routes_repository.get_by_id(db_session, "route-1")
    assert stored.conditions["severity"] == ["warning"]


async def test_upsert_update_clears_active_hours(db_session: AsyncSession):
    ah = ActiveHours(start="09:00", end="17:00")
    await routes_service.upsert_route(db_session, _body(active_hours=ah))
    await routes_service.upsert_route(db_session, _body(active_hours=None))

    stored = await routes_repository.get_by_id(db_session, "route-1")
    assert stored.active_hours is None


# ---------------------------------------------------------------------------
# Isolation — multiple routes do not interfere
# ---------------------------------------------------------------------------

async def test_upsert_version_independent_per_route(db_session: AsyncSession):
    await routes_service.upsert_route(db_session, _body(id="r1"))
    await routes_service.upsert_route(db_session, _body(id="r2"))
    await routes_service.upsert_route(db_session, _body(id="r1", priority=99))  # update only r1

    r1 = await routes_repository.get_by_id(db_session, "r1")
    r2 = await routes_repository.get_by_id(db_session, "r2")
    assert r1.version == 2
    assert r2.version == 1
