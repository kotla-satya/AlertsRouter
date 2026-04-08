"""HTTP integration tests for POST /alerts and GET /alerts."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from tests.helpers import assert_validation_error

ALERT = {
    "id": "alert-1",
    "severity": "critical",
    "service": "payment-api",
    "group": "backend",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "labels": {"env": "prod"},
}

MATCHING_ROUTE = {
    "id": "route-1",
    "conditions": {},  # matches everything
    "target": {"type": "slack", "channel": "#alerts"},
    "priority": 10,
    "suppression_window_seconds": 60,
}

NON_MATCHING_ROUTE = {
    "id": "route-nm",
    "conditions": {"severity": ["warning"], "service": [], "group": [], "labels": {}},
    "target": {"type": "email", "address": "ops@example.com"},
    "priority": 5,
}


async def test_submit_alert_no_routes(client: AsyncClient):
    resp = await client.post("/alerts", json=ALERT)
    assert resp.status_code == 200
    body = resp.json()
    assert body["alert_id"] == "alert-1"
    assert body["routed_to"] is None
    assert body["suppressed"] is False
    assert body["matched_routes"] == []
    assert body["evaluation_details"]["total_routes_evaluated"] == 0
    assert body["evaluation_details"]["routes_matched"] == 0


async def test_submit_alert_matched(client: AsyncClient):
    await client.post("/routes", json=MATCHING_ROUTE)

    resp = await client.post("/alerts", json=ALERT)
    assert resp.status_code == 200
    body = resp.json()
    assert body["alert_id"] == "alert-1"
    assert body["suppressed"] is False
    assert body["routed_to"]["route_id"] == "route-1"
    assert body["routed_to"]["target"]["type"] == "slack"
    assert "route-1" in body["matched_routes"]
    assert body["evaluation_details"]["routes_matched"] == 1
    assert body["evaluation_details"]["suppression_applied"] is False


async def test_submit_alert_no_match(client: AsyncClient):
    await client.post("/routes", json=NON_MATCHING_ROUTE)

    # severity=critical won't match route that requires severity=warning
    resp = await client.post("/alerts", json=ALERT)
    assert resp.status_code == 200
    body = resp.json()
    assert body["routed_to"] is None
    assert body["suppressed"] is False
    assert body["matched_routes"] == []
    assert body["evaluation_details"]["routes_matched"] == 0
    assert body["evaluation_details"]["routes_not_matched"] == 1


async def test_submit_alert_no_match_after_route_deleted(client: AsyncClient):
    # Route matches — first alert is routed
    await client.post("/routes", json=MATCHING_ROUTE)
    first = await client.post("/alerts", json=ALERT)
    assert first.json()["routed_to"] is not None

    # Delete the route
    await client.delete(f"/routes/{MATCHING_ROUTE['id']}")

    # Same alert again — no routes exist, must be unrouted
    resp = await client.post("/alerts", json={**ALERT, "id": "alert-2"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["routed_to"] is None
    assert body["suppressed"] is False
    assert body["matched_routes"] == []
    assert body["evaluation_details"]["total_routes_evaluated"] == 0


async def test_submit_alert_suppressed(client: AsyncClient):
    await client.post("/routes", json=MATCHING_ROUTE)

    # First alert — routed normally
    first = await client.post("/alerts", json=ALERT)
    assert first.json()["suppressed"] is False

    # Second alert with same service — within suppression window
    second = await client.post("/alerts", json={**ALERT, "id": "alert-2"})
    body = second.json()
    assert body["suppressed"] is True
    assert body["routed_to"]["route_id"] == "route-1"
    assert body["routed_to"]["target"]["type"] == "slack"
    assert body["matched_routes"] == ["route-1"]
    assert body["suppression_reason"] is not None
    assert body["evaluation_details"]["suppression_applied"] is True


async def test_submit_alert_suppression_different_service(client: AsyncClient):
    await client.post("/routes", json=MATCHING_ROUTE)

    # First alert from payment-api — routed and suppression window set
    await client.post("/alerts", json=ALERT)

    # Alert from a different service — should NOT be suppressed
    other_alert = {**ALERT, "id": "alert-other", "service": "auth-service"}
    resp = await client.post("/alerts", json=other_alert)
    body = resp.json()
    assert body["suppressed"] is False
    assert body["routed_to"] is not None


# ---------------------------------------------------------------------------
# Suppression window border conditions (time-frozen)
#
# Route: suppression_window_seconds=60
# First alert at T0 → routed, suppression record written at T0
# Second alert at T0+elapsed:
#   elapsed=59s → still inside window  → suppressed
#   elapsed=60s → exactly at boundary  → NOT suppressed (window expired)
#   elapsed=61s → just past boundary   → NOT suppressed
# ---------------------------------------------------------------------------

_SUPPRESS_BORDER_ROUTE = {
    "id": "route-border",
    "conditions": {},
    "target": {"type": "slack", "channel": "#alerts"},
    "priority": 10,
    "suppression_window_seconds": 60,
}

_T0 = datetime(2026, 4, 7, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("elapsed_seconds, expect_suppressed", [
    (59, True),   # 1 second before expiry — still in window
    (60, False),  # exactly at boundary   — window just expired
    (61, False),  # 1 second after expiry — no longer suppressed
])
async def test_suppression_window_border(
    client: AsyncClient, elapsed_seconds: int, expect_suppressed: bool
):
    await client.post("/routes", json=_SUPPRESS_BORDER_ROUTE)

    # First alert at T0 — sets suppression record with last_routed_at = T0
    await _submit_at(client, _T0)

    # Second alert at T0 + elapsed_seconds
    resp = await _submit_at(client, _T0 + timedelta(seconds=elapsed_seconds), {**ALERT, "id": "alert-2"})
    body = resp.json()

    assert body["suppressed"] is expect_suppressed
    assert body["routed_to"]["route_id"] == "route-border"  # always set (routed or suppressed)
    if expect_suppressed:
        assert body["suppression_reason"] is not None
        assert "route-border" in body["matched_routes"]
    else:
        assert body["suppression_reason"] is None
        assert "route-border" in body["matched_routes"]


async def test_submit_alert_invalid_body(client: AsyncClient):
    bad = {k: v for k, v in ALERT.items() if k != "severity"}  # missing required field
    resp = await client.post("/alerts", json=bad)
    assert_validation_error(resp, field="severity")


async def test_submit_alert_naive_timestamp_rejected(client: AsyncClient):
    # Timestamps without timezone info must be rejected (AwareDatetime)
    naive = {**ALERT, "timestamp": "2026-04-06T10:00:00"}  # no timezone
    resp = await client.post("/alerts", json=naive)
    assert_validation_error(resp, field="timestamp")


# ---------------------------------------------------------------------------
# GET /alerts/{id}
# ---------------------------------------------------------------------------

async def test_get_alert_by_id(client: AsyncClient):
    await client.post("/routes", json=MATCHING_ROUTE)
    post_body = (await client.post("/alerts", json=ALERT)).json()

    resp = await client.get(f"/alerts/{ALERT['id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["alert_id"] == post_body["alert_id"]
    assert body["routed_to"] == post_body["routed_to"]
    assert body["suppressed"] == post_body["suppressed"]
    assert body["matched_routes"] == post_body["matched_routes"]


async def test_get_alert_by_id_not_found(client: AsyncClient):
    resp = await client.get("/alerts/nonexistent")
    assert resp.status_code == 404
    assert resp.json() == {"error": "alert not found"}


# ---------------------------------------------------------------------------
# GET /alerts (list with filters)
# ---------------------------------------------------------------------------

async def test_get_alerts_no_filter(client: AsyncClient):
    await client.post("/routes", json=MATCHING_ROUTE)
    await client.post("/alerts", json=ALERT)
    await client.post("/alerts", json={**ALERT, "id": "alert-other", "service": "auth-service"})

    resp = await client.get("/alerts")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["alerts"]) == 2


async def test_get_alerts_filter_service(client: AsyncClient):
    await client.post("/routes", json=MATCHING_ROUTE)
    await client.post("/alerts", json=ALERT)
    await client.post("/alerts", json={**ALERT, "id": "alert-other", "service": "auth-service"})

    resp = await client.get("/alerts?service=payment-api")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["alerts"][0]["alert_id"] == "alert-1"


async def test_get_alerts_filter_severity(client: AsyncClient):
    await client.post("/routes", json=MATCHING_ROUTE)
    await client.post("/alerts", json=ALERT)  # critical
    await client.post("/alerts", json={**ALERT, "id": "alert-w", "severity": "warning"})

    resp = await client.get("/alerts?severity=warning")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["alerts"][0]["alert_id"] == "alert-w"


async def test_get_alerts_filter_routed_true(client: AsyncClient):
    await client.post("/routes", json=MATCHING_ROUTE)
    await client.post("/alerts", json=ALERT)  # routed

    resp = await client.get("/alerts?routed=true")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


async def test_get_alerts_filter_suppressed_true(client: AsyncClient):
    await client.post("/routes", json=MATCHING_ROUTE)
    await client.post("/alerts", json=ALERT)  # first — routed
    await client.post("/alerts", json={**ALERT, "id": "alert-2"})  # second — suppressed

    resp = await client.get("/alerts?suppressed=true")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["alerts"][0]["alert_id"] == "alert-2"


async def test_get_alerts_combined_filter(client: AsyncClient):
    await client.post("/routes", json=MATCHING_ROUTE)
    await client.post("/alerts", json=ALERT)  # critical + payment-api
    await client.post("/alerts", json={**ALERT, "id": "alert-w", "severity": "warning"})

    # AND: only alert with both severity=critical AND service=payment-api
    resp = await client.get("/alerts?severity=critical&service=payment-api")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["alerts"][0]["alert_id"] == "alert-1"


async def test_get_alerts_empty_result(client: AsyncClient):
    resp = await client.get("/alerts?service=nonexistent-service")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["alerts"] == []


# ---------------------------------------------------------------------------
# Active hours helpers
# ---------------------------------------------------------------------------

async def _submit_at(client: AsyncClient, frozen_now: datetime, alert: dict | None = None):
    """POST /alerts with datetime.now frozen to frozen_now."""
    with patch("app.services.alerts_service.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        return await client.post("/alerts", json=alert if alert is not None else ALERT)


# ---------------------------------------------------------------------------
# Active hours — America/New_York (UTC-4 in April / EDT)
#
# Route window: 09:00–17:00 America/New_York
#   14:00 UTC = 10:00 EDT  → inside  → alert routed
#   02:00 UTC = 22:00 EDT  → outside → route skipped, alert unrouted
# ---------------------------------------------------------------------------

_NY_ROUTE = {
    "id": "route-ny",
    "conditions": {},
    "target": {"type": "slack", "channel": "#alerts"},
    "priority": 10,
    "active_hours": {"start": "09:00", "end": "17:00", "timezone": "America/New_York"},
}

# 14:00 UTC = 10:00 EDT (inside window)
_INSIDE_NY = datetime(2026, 4, 6, 14, 0, 0, tzinfo=timezone.utc)
# 02:00 UTC = 22:00 EDT (outside window)
_OUTSIDE_NY = datetime(2026, 4, 6, 2, 0, 0, tzinfo=timezone.utc)


async def test_alert_during_active_hours_new_york_is_routed(client: AsyncClient):
    await client.post("/routes", json=_NY_ROUTE)
    resp = await _submit_at(client, _INSIDE_NY)
    assert resp.status_code == 200
    body = resp.json()
    assert body["routed_to"]["route_id"] == "route-ny"
    assert body["suppressed"] is False


async def test_alert_outside_active_hours_new_york_is_unrouted(client: AsyncClient):
    await client.post("/routes", json=_NY_ROUTE)
    resp = await _submit_at(client, _OUTSIDE_NY)
    assert resp.status_code == 200
    body = resp.json()
    assert body["routed_to"] is None
    assert body["matched_routes"] == []


# ---------------------------------------------------------------------------
# Active hours — Asia/Kolkata (UTC+5:30 / IST, no DST)
#
# Route window: 09:00–17:00 Asia/Kolkata
#   04:00 UTC = 09:30 IST  → inside  → alert routed
#   14:00 UTC = 19:30 IST  → outside → route skipped, alert unrouted
# ---------------------------------------------------------------------------

_IST_ROUTE = {
    "id": "route-ist",
    "conditions": {},
    "target": {"type": "slack", "channel": "#alerts"},
    "priority": 10,
    "active_hours": {"start": "09:00", "end": "17:00", "timezone": "Asia/Kolkata"},
}

# 04:00 UTC = 09:30 IST (inside window)
_INSIDE_IST = datetime(2026, 4, 6, 4, 0, 0, tzinfo=timezone.utc)
# 14:00 UTC = 19:30 IST (outside window)
_OUTSIDE_IST = datetime(2026, 4, 6, 14, 0, 0, tzinfo=timezone.utc)


async def test_alert_during_active_hours_kolkata_is_routed(client: AsyncClient):
    await client.post("/routes", json=_IST_ROUTE)
    resp = await _submit_at(client, _INSIDE_IST)
    assert resp.status_code == 200
    body = resp.json()
    assert body["routed_to"]["route_id"] == "route-ist"
    assert body["suppressed"] is False


async def test_alert_outside_active_hours_kolkata_is_unrouted(client: AsyncClient):
    await client.post("/routes", json=_IST_ROUTE)
    resp = await _submit_at(client, _OUTSIDE_IST)
    assert resp.status_code == 200
    body = resp.json()
    assert body["routed_to"] is None
    assert body["matched_routes"] == []


# ---------------------------------------------------------------------------
# Active hours + suppression combined (America/New_York)
#
# Route: 09:00–17:00 EDT, suppression_window_seconds=300
#
#   1st alert inside window  → routed, suppression record written
#   2nd alert inside window  → suppressed (same service, within window)
#   3rd alert outside window → unrouted (route inactive, no suppression check)
# ---------------------------------------------------------------------------

_NY_SUPPRESS_ROUTE = {
    "id": "route-ny-suppress",
    "conditions": {},
    "target": {"type": "slack", "channel": "#alerts"},
    "priority": 10,
    "suppression_window_seconds": 300,
    "active_hours": {"start": "09:00", "end": "17:00", "timezone": "America/New_York"},
}


async def test_active_hours_first_alert_routed(client: AsyncClient):
    await client.post("/routes", json=_NY_SUPPRESS_ROUTE)
    resp = await _submit_at(client, _INSIDE_NY)
    body = resp.json()
    assert body["routed_to"]["route_id"] == "route-ny-suppress"
    assert body["suppressed"] is False


async def test_active_hours_second_alert_suppressed(client: AsyncClient):
    await client.post("/routes", json=_NY_SUPPRESS_ROUTE)
    await _submit_at(client, _INSIDE_NY)  # first — routed, sets suppression record

    resp = await _submit_at(client, _INSIDE_NY, {**ALERT, "id": "alert-2"})
    body = resp.json()
    assert body["suppressed"] is True
    assert body["routed_to"]["route_id"] == "route-ny-suppress"
    assert body["suppression_reason"] is not None
    assert body["evaluation_details"]["suppression_applied"] is True


async def test_active_hours_outside_window_not_suppressed(client: AsyncClient):
    await client.post("/routes", json=_NY_SUPPRESS_ROUTE)
    await _submit_at(client, _INSIDE_NY)  # first — routed inside window

    # Outside active hours: route doesn't match at all — not suppressed, just unrouted
    resp = await _submit_at(client, _OUTSIDE_NY, {**ALERT, "id": "alert-3"})
    body = resp.json()
    assert body["routed_to"] is None
    assert body["suppressed"] is False
    assert body["matched_routes"] == []


# ---------------------------------------------------------------------------
# Route conditions — service glob, group, labels, severity
# ---------------------------------------------------------------------------

def _route_with_conditions(conditions: dict) -> dict:
    return {
        "id": "route-cond",
        "conditions": conditions,
        "target": {"type": "slack", "channel": "#alerts"},
        "priority": 10,
    }


async def test_condition_service_glob_match(client: AsyncClient):
    # pattern "payment-*" should match "payment-api"
    await client.post("/routes", json=_route_with_conditions({"service": ["payment-*"]}))
    resp = await client.post("/alerts", json=ALERT)  # service="payment-api"
    body = resp.json()
    assert body["routed_to"]["route_id"] == "route-cond"
    assert "route-cond" in body["matched_routes"]


async def test_condition_service_glob_no_match(client: AsyncClient):
    # pattern "payment-*" must not match "auth-service"
    await client.post("/routes", json=_route_with_conditions({"service": ["payment-*"]}))
    resp = await client.post("/alerts", json={**ALERT, "id": "alert-auth", "service": "auth-service"})
    body = resp.json()
    assert body["routed_to"] is None
    assert body["matched_routes"] == []


@pytest.mark.parametrize("service, should_match", [
    ("payment-api",   True),   # ends in -api → match
    ("auth-api",      True),   # ends in -api → match
    ("auth-service",  False),  # doesn't end in -api → no match
])
async def test_condition_service_leading_wildcard(client: AsyncClient, service: str, should_match: bool):
    await client.post("/routes", json=_route_with_conditions({"service": ["*-api"]}))
    body = (await client.post("/alerts", json={**ALERT, "service": service})).json()
    if should_match:
        assert body["routed_to"]["route_id"] == "route-cond"
    else:
        assert body["routed_to"] is None


@pytest.mark.parametrize("service, should_match", [
    ("payment-api",     True),   # matches payment-*
    ("auth-service",    True),   # matches auth-*
    ("billing-service", False),  # matches neither pattern
])
async def test_condition_service_multiple_patterns(client: AsyncClient, service: str, should_match: bool):
    await client.post("/routes", json=_route_with_conditions({"service": ["payment-*", "auth-*"]}))
    body = (await client.post("/alerts", json={**ALERT, "service": service})).json()
    if should_match:
        assert body["routed_to"]["route_id"] == "route-cond"
    else:
        assert body["routed_to"] is None


async def test_condition_group_match(client: AsyncClient):
    await client.post("/routes", json=_route_with_conditions({"group": ["backend"]}))
    resp = await client.post("/alerts", json=ALERT)  # group="backend"
    body = resp.json()
    assert body["routed_to"]["route_id"] == "route-cond"


@pytest.mark.parametrize("group, should_match", [
    ("backend",  True),   # in list
    ("frontend", True),   # in list
    ("data",     True),   # in list
    ("infra",    False),  # not in list
])
async def test_condition_group_multiple_groups(client: AsyncClient, group: str, should_match: bool):
    await client.post("/routes", json=_route_with_conditions({"group": ["backend", "frontend", "data"]}))
    body = (await client.post("/alerts", json={**ALERT, "group": group})).json()
    if should_match:
        assert body["routed_to"]["route_id"] == "route-cond"
    else:
        assert body["routed_to"] is None


async def test_condition_group_no_match(client: AsyncClient):
    await client.post("/routes", json=_route_with_conditions({"group": ["backend"]}))
    resp = await client.post("/alerts", json={**ALERT, "id": "alert-fe", "group": "frontend"})
    body = resp.json()
    assert body["routed_to"] is None
    assert body["matched_routes"] == []


async def test_condition_labels_match(client: AsyncClient):
    # conditions.labels is a subset check — alert can have extra labels
    await client.post("/routes", json=_route_with_conditions({"labels": {"env": "prod"}}))
    alert = {**ALERT, "labels": {"env": "prod", "region": "us-east-1"}}
    body = (await client.post("/alerts", json=alert)).json()
    assert body["routed_to"]["route_id"] == "route-cond"


@pytest.mark.parametrize("labels, should_match", [
    pytest.param({"env": "prod", "region": "us-east-1"},                        True,  id="all_required_present"),
    pytest.param({"env": "prod", "region": "us-east-1", "team": "payments"},    True,  id="extra_label_still_matches"),
    pytest.param({"env": "prod"},                                                False, id="missing_required_label"),
    pytest.param({"env": "prod", "region": "eu-west-1"},                        False, id="wrong_label_value"),
])
async def test_condition_labels_multiple_required(client: AsyncClient, labels: dict, should_match: bool):
    # route requires env=prod AND region=us-east-1 — all conditions must be satisfied
    await client.post("/routes", json=_route_with_conditions({"labels": {"env": "prod", "region": "us-east-1"}}))
    body = (await client.post("/alerts", json={**ALERT, "labels": labels})).json()
    if should_match:
        assert body["routed_to"]["route_id"] == "route-cond"
    else:
        assert body["routed_to"] is None


async def test_condition_labels_no_match(client: AsyncClient):
    await client.post("/routes", json=_route_with_conditions({"labels": {"env": "prod"}}))
    alert = {**ALERT, "labels": {"env": "staging"}}
    body = (await client.post("/alerts", json=alert)).json()
    assert body["routed_to"] is None
    assert body["matched_routes"] == []


async def test_condition_labels_missing_key_no_match(client: AsyncClient):
    # route requires env=prod but alert has no labels at all
    await client.post("/routes", json=_route_with_conditions({"labels": {"env": "prod"}}))
    alert = {**ALERT, "labels": {}}
    body = (await client.post("/alerts", json=alert)).json()
    assert body["routed_to"] is None


async def test_condition_severity_match(client: AsyncClient):
    await client.post("/routes", json=_route_with_conditions({"severity": ["warning", "critical"]}))
    resp = await client.post("/alerts", json={**ALERT, "severity": "warning"})
    body = resp.json()
    assert body["routed_to"]["route_id"] == "route-cond"


async def test_condition_severity_no_match(client: AsyncClient):
    await client.post("/routes", json=_route_with_conditions({"severity": ["warning"]}))
    resp = await client.post("/alerts", json={**ALERT, "severity": "info"})
    body = resp.json()
    assert body["routed_to"] is None
    assert body["matched_routes"] == []


async def test_condition_all_fields_combined_match(client: AsyncClient):
    # All four condition types must pass simultaneously
    conds = {
        "severity": ["critical"],
        "service": ["payment-*"],
        "group": ["backend"],
        "labels": {"env": "prod"},
    }
    await client.post("/routes", json=_route_with_conditions(conds))
    resp = await client.post("/alerts", json=ALERT)  # matches all four
    assert resp.json()["routed_to"]["route_id"] == "route-cond"


async def test_condition_all_fields_combined_partial_no_match(client: AsyncClient):
    # Same conditions — but alert has wrong group → no match
    conds = {
        "severity": ["critical"],
        "service": ["payment-*"],
        "group": ["backend"],
        "labels": {"env": "prod"},
    }
    await client.post("/routes", json=_route_with_conditions(conds))
    resp = await client.post("/alerts", json={**ALERT, "group": "frontend"})
    assert resp.json()["routed_to"] is None
