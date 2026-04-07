from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.routing_config import RoutingConfig
from app.repositories import routes_repository

_NOW = datetime.now(timezone.utc)

ROUTE_DATA = dict(
    id="repo-test-1",
    conditions={"severity": ["critical"], "service": [], "group": [], "labels": {}},
    target={"type": "slack", "channel": "#ops"},
    priority=10,
    suppression_window_seconds=0,
    active_hours=None,
)


def _make_route(**overrides) -> RoutingConfig:
    data = {**ROUTE_DATA, **overrides}
    return RoutingConfig(**data)


async def test_get_by_id_not_found(db_session: AsyncSession):
    result = await routes_repository.get_by_id(db_session, "does-not-exist")
    assert result is None


async def test_add_and_get_by_id(db_session: AsyncSession):
    await routes_repository.add(db_session, _make_route())
    found = await routes_repository.get_by_id(db_session, "repo-test-1")
    assert found is not None
    assert found.id == "repo-test-1"
    assert found.priority == 10


async def test_update_fields(db_session: AsyncSession):
    await routes_repository.add(db_session, _make_route())
    route = await routes_repository.get_by_id(db_session, "repo-test-1")
    await routes_repository.update_fields(db_session, route, {"priority": 99})
    updated = await routes_repository.get_by_id(db_session, "repo-test-1")
    assert updated.priority == 99


async def test_list_all_ordered_by_priority(db_session: AsyncSession):
    await routes_repository.add(db_session, _make_route(id="low", priority=1))
    await routes_repository.add(db_session, _make_route(id="high", priority=50))
    await routes_repository.add(db_session, _make_route(id="mid", priority=20))

    rows = await routes_repository.list_all(db_session)
    assert [r.id for r in rows] == ["high", "mid", "low"]


async def test_delete_route(db_session: AsyncSession):
    await routes_repository.add(db_session, _make_route())
    route = await routes_repository.get_by_id(db_session, "repo-test-1")
    assert route is not None

    await routes_repository.delete(db_session, route)
    assert await routes_repository.get_by_id(db_session, "repo-test-1") is None


async def test_version_starts_at_1(db_session: AsyncSession):
    await routes_repository.add(db_session, _make_route())
    route = await routes_repository.get_by_id(db_session, "repo-test-1")
    assert route.version == 1


async def test_version_increments_on_update(db_session: AsyncSession):
    await routes_repository.add(db_session, _make_route())
    route = await routes_repository.get_by_id(db_session, "repo-test-1")
    await routes_repository.update_fields(db_session, route, {"priority": 99, "version": route.version + 1})
    updated = await routes_repository.get_by_id(db_session, "repo-test-1")
    assert updated.version == 2


async def test_version_independent_per_route(db_session: AsyncSession):
    await routes_repository.add(db_session, _make_route(id="r1"))
    await routes_repository.add(db_session, _make_route(id="r2"))
    r1 = await routes_repository.get_by_id(db_session, "r1")
    await routes_repository.update_fields(db_session, r1, {"priority": 99, "version": r1.version + 1})

    r1_updated = await routes_repository.get_by_id(db_session, "r1")
    r2 = await routes_repository.get_by_id(db_session, "r2")
    assert r1_updated.version == 2
    assert r2.version == 1
