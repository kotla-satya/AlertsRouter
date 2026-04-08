from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from sqlalchemy.exc import SQLAlchemyError

from tests.helpers import assert_validation_error

SLACK_ROUTE = {
    "id": "route-1",
    "conditions": {
        "severity": ["critical"],
        "service": ["payment-*"],
        "group": ["backend"],
        "labels": {"env": "prod"},
    },
    "target": {"type": "slack", "channel": "#alerts"},
    "priority": 10,
    "suppression_window_seconds": 60,
    "active_hours": {"start": "09:00", "end": "17:00", "timezone": "UTC"},
}

EMAIL_ROUTE = {
    "id": "route-2",
    "conditions": {},
    "target": {"type": "email", "address": "ops@example.com"},
    "priority": 5,
}


async def test_create_route(client: AsyncClient):
    resp = await client.post("/routes", json=SLACK_ROUTE)
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] == "route-1"
    assert body["created"] is True


async def test_update_existing_route(client: AsyncClient):
    await client.post("/routes", json=SLACK_ROUTE)

    updated = {**SLACK_ROUTE, "priority": 99}
    resp = await client.post("/routes", json=updated)
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] == "route-1"
    assert body["created"] is False

    # Verify the updated value is persisted
    list_resp = await client.get("/routes")
    routes = list_resp.json()
    assert routes[0]["priority"] == 99


async def test_list_routes_empty(client: AsyncClient):
    resp = await client.get("/routes")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_routes_ordered_by_priority(client: AsyncClient):
    await client.post("/routes", json=EMAIL_ROUTE)   # priority 5
    await client.post("/routes", json=SLACK_ROUTE)   # priority 10

    resp = await client.get("/routes")
    assert resp.status_code == 200
    routes = resp.json()
    assert len(routes) == 2
    assert routes[0]["id"] == "route-1"  # priority 10 first
    assert routes[1]["id"] == "route-2"  # priority 5 second


async def test_delete_route(client: AsyncClient):
    await client.post("/routes", json=SLACK_ROUTE)

    resp = await client.delete("/routes/route-1")
    assert resp.status_code == 200
    assert resp.json() == {"id": "route-1", "deleted": True}

    list_resp = await client.get("/routes")
    assert list_resp.json() == []


async def test_delete_route_not_found(client: AsyncClient):
    resp = await client.delete("/routes/nonexistent")
    assert resp.status_code == 404
    assert resp.json() == {"error": "route not found"}


# --- Validation (400) tests ---

WEBHOOK_ROUTE = {
    "id": "route-w",
    "conditions": {},
    "target": {"type": "webhook", "url": "https://example.com/hook"},
    "priority": 1,
}


async def test_create_route_empty_id(client: AsyncClient):
    resp = await client.post("/routes", json={**SLACK_ROUTE, "id": ""})
    assert_validation_error(resp, field="id")


async def test_create_route_invalid_priority(client: AsyncClient):
    resp = await client.post("/routes", json={**SLACK_ROUTE, "priority": 0})
    assert_validation_error(resp, field="priority")


async def test_create_route_negative_suppression(client: AsyncClient):
    resp = await client.post("/routes", json={**SLACK_ROUTE, "suppression_window_seconds": -1})
    assert_validation_error(resp, field="suppression_window_seconds")


async def test_create_route_invalid_active_hours_format(client: AsyncClient):
    bad = {**SLACK_ROUTE, "active_hours": {"start": "9:00", "end": "17:00"}}
    resp = await client.post("/routes", json=bad)
    assert_validation_error(resp, field="start")


async def test_create_route_active_hours_start_eq_end(client: AsyncClient):
    bad = {**SLACK_ROUTE, "active_hours": {"start": "10:00", "end": "10:00"}}
    resp = await client.post("/routes", json=bad)
    assert_validation_error(resp, field="active_hours")


async def test_create_route_invalid_timezone(client: AsyncClient):
    bad = {**SLACK_ROUTE, "active_hours": {"start": "09:00", "end": "17:00", "timezone": "InvalidTZ"}}
    resp = await client.post("/routes", json=bad)
    assert_validation_error(resp, field="timezone")


async def test_create_route_valid_iana_timezone(client: AsyncClient):
    route = {**SLACK_ROUTE, "active_hours": {"start": "09:00", "end": "17:00", "timezone": "America/New_York"}}
    resp = await client.post("/routes", json=route)
    assert resp.status_code == 201


async def test_create_route_invalid_webhook_url(client: AsyncClient):
    bad = {**WEBHOOK_ROUTE, "target": {"type": "webhook", "url": "not-a-url"}}
    resp = await client.post("/routes", json=bad)
    assert_validation_error(resp, field="url")


# --- Target type tests ---

_BASE = {
    "id": "route-target",
    "conditions": {},
    "priority": 1,
}


async def test_create_route_target_slack(client: AsyncClient):
    resp = await client.post("/routes", json={**_BASE, "target": {"type": "slack", "channel": "#ops"}})
    assert resp.status_code == 201
    routes = (await client.get("/routes")).json()
    assert routes[0]["target"]["type"] == "slack"
    assert routes[0]["target"]["channel"] == "#ops"


async def test_create_route_target_email(client: AsyncClient):
    resp = await client.post("/routes", json={**_BASE, "target": {"type": "email", "address": "ops@example.com"}})
    assert resp.status_code == 201
    routes = (await client.get("/routes")).json()
    assert routes[0]["target"]["type"] == "email"
    assert routes[0]["target"]["address"] == "ops@example.com"


async def test_create_route_target_pagerduty(client: AsyncClient):
    resp = await client.post("/routes", json={**_BASE, "target": {"type": "pagerduty", "service_key": "abc123"}})
    assert resp.status_code == 201
    routes = (await client.get("/routes")).json()
    assert routes[0]["target"]["type"] == "pagerduty"
    assert routes[0]["target"]["service_key"] == "abc123"


async def test_create_route_target_webhook(client: AsyncClient):
    resp = await client.post("/routes", json={**_BASE, "target": {"type": "webhook", "url": "https://hook.example.com"}})
    assert resp.status_code == 201
    routes = (await client.get("/routes")).json()
    assert routes[0]["target"]["type"] == "webhook"
    assert routes[0]["target"]["url"] == "https://hook.example.com"


async def test_create_route_target_webhook_with_headers(client: AsyncClient):
    target = {"type": "webhook", "url": "https://hook.example.com", "headers": {"X-Token": "secret"}}
    resp = await client.post("/routes", json={**_BASE, "target": target})
    assert resp.status_code == 201
    routes = (await client.get("/routes")).json()
    assert routes[0]["target"]["headers"] == {"X-Token": "secret"}


# --- Invalid target type / missing required fields ---

async def test_create_route_invalid_target_type(client: AsyncClient):
    bad = {**_BASE, "target": {"type": "sms", "number": "+1234567890"}}
    resp = await client.post("/routes", json=bad)
    assert_validation_error(resp, field="target")


async def test_create_route_slack_missing_channel(client: AsyncClient):
    bad = {**_BASE, "target": {"type": "slack"}}
    resp = await client.post("/routes", json=bad)
    assert_validation_error(resp, field="channel")


async def test_create_route_email_invalid_address(client: AsyncClient):
    bad = {**_BASE, "target": {"type": "email", "address": "not-an-email"}}
    resp = await client.post("/routes", json=bad)
    assert_validation_error(resp, field="address")


async def test_create_route_email_missing_address(client: AsyncClient):
    bad = {**_BASE, "target": {"type": "email"}}
    resp = await client.post("/routes", json=bad)
    assert_validation_error(resp, field="address")


async def test_create_route_pagerduty_missing_service_key(client: AsyncClient):
    bad = {**_BASE, "target": {"type": "pagerduty"}}
    resp = await client.post("/routes", json=bad)
    assert_validation_error(resp, field="service_key")


async def test_create_route_webhook_missing_url(client: AsyncClient):
    bad = {**_BASE, "target": {"type": "webhook"}}
    resp = await client.post("/routes", json=bad)
    assert_validation_error(resp, field="url")


# --- DB failure tests ---

async def test_db_failure_on_post_returns_500(client: AsyncClient):
    with patch(
        "app.repositories.routes_repository.get_by_id",
        new=AsyncMock(side_effect=SQLAlchemyError("connection refused")),
    ):
        resp = await client.post("/routes", json=SLACK_ROUTE)
    assert resp.status_code == 500
    assert resp.json() == {"error": "database error"}


async def test_db_failure_on_get_returns_500(client: AsyncClient):
    with patch(
        "app.repositories.routes_repository.list_all",
        new=AsyncMock(side_effect=SQLAlchemyError("connection refused")),
    ):
        resp = await client.get("/routes")
    assert resp.status_code == 500
    assert resp.json() == {"error": "database error"}


async def test_db_failure_on_delete_returns_500(client: AsyncClient):
    with patch(
        "app.repositories.routes_repository.get_by_id",
        new=AsyncMock(side_effect=SQLAlchemyError("connection refused")),
    ):
        resp = await client.delete("/routes/route-1")
    assert resp.status_code == 500
    assert resp.json() == {"error": "database error"}



