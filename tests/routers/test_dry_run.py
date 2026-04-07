"""Integration tests for POST /test (dry-run alert routing)."""
from datetime import datetime, timezone

from httpx import AsyncClient

from tests.helpers import assert_validation_error

ALERT = {
    "id": "alert-1",
    "severity": "critical",
    "service": "payment-api",
    "group": "backend",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "labels": {},
}

ROUTE = {
    "id": "route-1",
    "conditions": {},
    "target": {"type": "slack", "channel": "#alerts"},
    "priority": 10,
    "suppression_window_seconds": 60,
}


async def test_dry_run_no_routes(client: AsyncClient):
    resp = await client.post("/test", json=ALERT)
    assert resp.status_code == 200
    body = resp.json()
    assert body["alert_id"] == "alert-1"
    assert body["routed_to"] is None
    assert body["suppressed"] is False
    assert body["matched_routes"] == []


async def test_dry_run_matched(client: AsyncClient):
    await client.post("/routes", json=ROUTE)

    resp = await client.post("/test", json=ALERT)
    assert resp.status_code == 200
    body = resp.json()
    assert body["routed_to"]["route_id"] == "route-1"
    assert body["suppressed"] is False
    assert "route-1" in body["matched_routes"]


async def test_dry_run_suppressed_by_real_alert(client: AsyncClient):
    await client.post("/routes", json=ROUTE)

    # A real POST /alerts sets the suppression window
    await client.post("/alerts", json=ALERT)

    # Dry-run correctly reflects that a second alert would be suppressed
    resp = await client.post("/test", json={**ALERT, "id": "alert-2"})
    body = resp.json()
    assert body["suppressed"] is True
    assert body["routed_to"]["route_id"] == "route-1"
    assert body["suppression_reason"] is not None


async def test_dry_run_does_not_store_alert(client: AsyncClient):
    await client.post("/test", json=ALERT)

    # Alert should NOT appear in the alerts store
    resp = await client.get(f"/alerts/{ALERT['id']}")
    assert resp.status_code == 404


async def test_dry_run_does_not_update_suppression(client: AsyncClient):
    await client.post("/routes", json=ROUTE)

    # First dry-run — should NOT set a suppression record
    first = await client.post("/test", json=ALERT)
    assert first.json()["suppressed"] is False

    # Second dry-run with same service — should also NOT be suppressed
    second = await client.post("/test", json={**ALERT, "id": "alert-2"})
    assert second.json()["suppressed"] is False


async def test_dry_run_invalid_body(client: AsyncClient):
    bad = {k: v for k, v in ALERT.items() if k != "severity"}
    resp = await client.post("/test", json=bad)
    assert_validation_error(resp, field="severity")
