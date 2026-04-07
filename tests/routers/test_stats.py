"""HTTP integration tests for GET /stats."""
from datetime import datetime, timezone

from httpx import AsyncClient

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

ROUTE_2 = {
    "id": "route-2",
    "conditions": {"severity": ["warning"], "service": [], "group": [], "labels": {}},
    "target": {"type": "email", "address": "ops@example.com"},
    "priority": 5,
}


async def test_stats_empty(client: AsyncClient):
    resp = await client.get("/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_alerts_processed"] == 0
    assert body["total_routed"] == 0
    assert body["total_suppressed"] == 0
    assert body["total_unrouted"] == 0
    assert body["by_severity"] == {}
    assert body["by_route"] == {}
    assert body["by_service"] == {}


async def test_stats_single_routed_alert(client: AsyncClient):
    await client.post("/routes", json=ROUTE)
    await client.post("/alerts", json=ALERT)

    resp = await client.get("/stats")
    body = resp.json()
    assert body["total_alerts_processed"] == 1
    assert body["total_routed"] == 1
    assert body["total_suppressed"] == 0
    assert body["total_unrouted"] == 0
    assert body["by_severity"]["critical"] == 1
    assert body["by_service"]["payment-api"] == 1
    assert body["by_route"]["route-1"]["total_routed"] == 1
    assert body["by_route"]["route-1"]["total_matched"] == 1
    assert body["by_route"]["route-1"]["total_suppressed"] == 0


async def test_stats_unrouted_alert(client: AsyncClient):
    # No routes — alert processed but unrouted
    await client.post("/alerts", json=ALERT)

    resp = await client.get("/stats")
    body = resp.json()
    assert body["total_alerts_processed"] == 1
    assert body["total_routed"] == 0
    assert body["total_suppressed"] == 0
    assert body["total_unrouted"] == 1
    assert body["by_route"] == {}


async def test_stats_suppressed_alert(client: AsyncClient):
    await client.post("/routes", json=ROUTE)
    await client.post("/alerts", json=ALERT)  # routed
    await client.post("/alerts", json={**ALERT, "id": "alert-2"})  # suppressed

    resp = await client.get("/stats")
    body = resp.json()
    assert body["total_alerts_processed"] == 2
    assert body["total_routed"] == 1
    assert body["total_suppressed"] == 1
    assert body["total_unrouted"] == 0
    assert body["by_route"]["route-1"]["total_routed"] == 1
    assert body["by_route"]["route-1"]["total_suppressed"] == 1
    assert body["by_route"]["route-1"]["total_matched"] == 2


async def test_stats_by_severity(client: AsyncClient):
    await client.post("/alerts", json=ALERT)  # critical
    await client.post("/alerts", json={**ALERT, "id": "alert-w", "severity": "warning"})
    await client.post("/alerts", json={**ALERT, "id": "alert-w2", "severity": "warning"})

    resp = await client.get("/stats")
    body = resp.json()
    assert body["by_severity"]["critical"] == 1
    assert body["by_severity"]["warning"] == 2
    assert "info" not in body["by_severity"]


async def test_stats_by_service(client: AsyncClient):
    await client.post("/alerts", json=ALERT)  # payment-api
    await client.post("/alerts", json={**ALERT, "id": "alert-auth", "service": "auth-service"})
    await client.post("/alerts", json={**ALERT, "id": "alert-auth2", "service": "auth-service"})

    resp = await client.get("/stats")
    body = resp.json()
    assert body["by_service"]["payment-api"] == 1
    assert body["by_service"]["auth-service"] == 2


async def test_stats_mixed_routed_suppressed_unrouted(client: AsyncClient):
    """total_routed counts only dispatched alerts; suppressed and unrouted are tracked separately."""
    route_critical = {
        "id": "route-critical",
        "conditions": {"severity": ["critical"]},
        "target": {"type": "slack", "channel": "#critical"},
        "priority": 10,
        "suppression_window_seconds": 300,
    }
    route_warning = {
        "id": "route-warning",
        "conditions": {"severity": ["warning"]},
        "target": {"type": "email", "address": "ops@example.com"},
        "priority": 5,
    }
    await client.post("/routes", json=route_critical)
    await client.post("/routes", json=route_warning)

    base = {
        "group": "backend",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "labels": {},
    }
    await client.post("/alerts", json={**base, "id": "a1", "severity": "critical", "service": "service-a"})
    await client.post("/alerts", json={**base, "id": "a2", "severity": "critical", "service": "service-a"})  # suppressed
    await client.post("/alerts", json={**base, "id": "a3", "severity": "warning",  "service": "service-b"})
    await client.post("/alerts", json={**base, "id": "a4", "severity": "info",     "service": "service-c"})  # unrouted

    resp = await client.get("/stats")
    body = resp.json()

    assert body["total_alerts_processed"] == 4
    assert body["total_routed"] == 2
    assert body["total_suppressed"] == 1
    assert body["total_unrouted"] == 1

    r_crit = body["by_route"]["route-critical"]
    assert r_crit["total_matched"] == 2
    assert r_crit["total_routed"] == 1
    assert r_crit["total_suppressed"] == 1

    r_warn = body["by_route"]["route-warning"]
    assert r_warn["total_matched"] == 1
    assert r_warn["total_routed"] == 1
    assert r_warn["total_suppressed"] == 0


async def test_stats_by_route_multiple_matched(client: AsyncClient):
    # route-1 matches everything, route-2 matches only warning
    await client.post("/routes", json=ROUTE)
    await client.post("/routes", json=ROUTE_2)

    # critical alert from payment-api — only route-1 matches
    await client.post("/alerts", json=ALERT)
    # warning alert from different service — both routes match; route-1 (priority 10) is primary
    # use a different service to avoid suppression window from the first alert
    await client.post("/alerts", json={**ALERT, "id": "alert-w", "severity": "warning", "service": "auth-service"})

    resp = await client.get("/stats")
    body = resp.json()
    r1 = body["by_route"]["route-1"]
    r2 = body["by_route"]["route-2"]
    assert r1["total_matched"] == 2   # matched both alerts
    assert r1["total_routed"] == 2    # primary for both
    assert r2["total_matched"] == 1   # matched only warning
    assert r2["total_routed"] == 0    # never primary (lower priority)
