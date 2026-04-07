"""Unit tests for pure functions in alerts_service — no DB, no HTTP."""
from datetime import datetime, timedelta, timezone

import pytest

import pytest

from app.models.routing_config import RoutingConfig
from app.schemas.alert import AlertCreate, EvaluationDetails
from app.schemas.routing_config import ActiveHours, RoutingConfigCondition
from app.services.alerts_service import (
    build_evaluation_details,
    find_matching_routes,
    is_suppressed,
    is_within_active_hours,
    match_conditions,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _alert(**overrides) -> AlertCreate:
    base = dict(
        id="alert-1",
        severity="critical",
        service="payment-api",
        group="backend",
        timestamp=datetime.now(timezone.utc),
        labels={"env": "prod"},
    )
    return AlertCreate(**{**base, **overrides})


def _conditions(**overrides) -> RoutingConfigCondition:
    base = dict(severity=[], service=[], group=[], labels={})
    return RoutingConfigCondition(**{**base, **overrides})


def _route(id: str = "r1", priority: int = 10, conditions: dict | None = None,
           active_hours: dict | None = None, suppression_window_seconds: int = 0) -> RoutingConfig:
    return RoutingConfig(
        id=id,
        conditions=conditions or {},
        target={"type": "slack", "channel": "#alerts"},
        priority=priority,
        suppression_window_seconds=suppression_window_seconds,
        active_hours=active_hours,
    )


# ---------------------------------------------------------------------------
# match_conditions
# ---------------------------------------------------------------------------

def test_match_conditions_empty_matches_all():
    assert match_conditions(_alert(), _conditions()) is True


def test_match_conditions_severity_match():
    assert match_conditions(_alert(severity="critical"), _conditions(severity=["critical", "warning"])) is True


def test_match_conditions_severity_no_match():
    assert match_conditions(_alert(severity="info"), _conditions(severity=["critical"])) is False


def test_match_conditions_service_glob_match():
    assert match_conditions(_alert(service="payment-api"), _conditions(service=["payment-*"])) is True


def test_match_conditions_service_exact_match():
    assert match_conditions(_alert(service="payment-api"), _conditions(service=["payment-api"])) is True


def test_match_conditions_service_no_match():
    assert match_conditions(_alert(service="auth-service"), _conditions(service=["payment-*"])) is False


def test_match_conditions_group_match():
    assert match_conditions(_alert(group="backend"), _conditions(group=["backend", "frontend"])) is True


def test_match_conditions_group_no_match():
    assert match_conditions(_alert(group="frontend"), _conditions(group=["backend"])) is False


def test_match_conditions_labels_subset_match():
    # conditions.labels is a subset of alert.labels — alert has extra labels, still matches
    alert = _alert(labels={"env": "prod", "team": "payments"})
    cond = _conditions(labels={"env": "prod"})
    assert match_conditions(alert, cond) is True


def test_match_conditions_labels_no_match():
    alert = _alert(labels={"env": "staging"})
    cond = _conditions(labels={"env": "prod"})
    assert match_conditions(alert, cond) is False


def test_match_conditions_labels_missing_key():
    # conditions require env=prod but alert has no labels at all → no match
    alert = _alert(labels={})
    cond = _conditions(labels={"env": "prod"})
    assert match_conditions(alert, cond) is False


def test_match_conditions_labels_empty_conditions_matches_any():
    # empty conditions.labels → no label filtering → always matches
    alert = _alert(labels={"env": "prod", "team": "payments"})
    cond = _conditions(labels={})
    assert match_conditions(alert, cond) is True


# ---------------------------------------------------------------------------
# is_within_active_hours
# ---------------------------------------------------------------------------

def _now_at(hour: int, minute: int = 0, tz: str = "UTC") -> datetime:
    import zoneinfo
    z = zoneinfo.ZoneInfo(tz)
    return datetime.now(z).replace(hour=hour, minute=minute, second=0, microsecond=0)


def test_active_hours_none_always_active():
    assert is_within_active_hours(None) is True


def test_active_hours_inside_window():
    ah = ActiveHours(start="09:00", end="17:00")
    assert is_within_active_hours(ah, now=_now_at(12)) is True


def test_active_hours_outside_window():
    ah = ActiveHours(start="09:00", end="17:00")
    assert is_within_active_hours(ah, now=_now_at(20)) is False


def test_active_hours_on_boundary_start():
    ah = ActiveHours(start="09:00", end="17:00")
    assert is_within_active_hours(ah, now=_now_at(9)) is True


def test_active_hours_on_boundary_end():
    ah = ActiveHours(start="09:00", end="17:00")
    assert is_within_active_hours(ah, now=_now_at(17)) is True  # end is inclusive


def test_active_hours_one_minute_before_start():
    ah = ActiveHours(start="09:00", end="17:00")
    assert is_within_active_hours(ah, now=_now_at(8, 59)) is False


def test_active_hours_one_minute_after_end():
    ah = ActiveHours(start="09:00", end="17:00")
    assert is_within_active_hours(ah, now=_now_at(17, 1)) is False


def test_active_hours_overnight_inside():
    ah = ActiveHours(start="22:00", end="06:00")
    assert is_within_active_hours(ah, now=_now_at(23)) is True


def test_active_hours_overnight_outside():
    ah = ActiveHours(start="22:00", end="06:00")
    assert is_within_active_hours(ah, now=_now_at(12)) is False


# ---------------------------------------------------------------------------
# is_within_active_hours — cross-timezone border conditions
#
# Route timezone defines when the window is active.
# Alert arrives as a UTC datetime (standard in this service).
# Each row: (route_tz, utc_hour, utc_minute, expected)
#
# America/New_York = EDT (UTC-4) in April 2026
#   09:00 EDT = 13:00 UTC  |  17:00 EDT = 21:00 UTC
#
# Asia/Kolkata = IST (UTC+5:30), no DST
#   09:00 IST = 03:30 UTC  |  17:00 IST = 11:30 UTC
#
# Europe/London = BST (UTC+1) in April 2026
#   09:00 BST = 08:00 UTC  |  17:00 BST = 16:00 UTC
# ---------------------------------------------------------------------------

_FIXED_DATE = datetime(2026, 4, 7, tzinfo=timezone.utc)  # Monday, DST already active


def _utc(hour: int, minute: int = 0) -> datetime:
    return _FIXED_DATE.replace(hour=hour, minute=minute, second=0)


@pytest.mark.parametrize("route_tz, utc_hour, utc_minute, expected", [
    # ── America/New_York (EDT = UTC-4) ──────────────────────────────────────
    ("America/New_York", 13,  0, True),   # 13:00 UTC = 09:00 EDT — start boundary
    ("America/New_York", 12, 59, False),  # 12:59 UTC = 08:59 EDT — 1 min before start
    ("America/New_York", 21,  0, True),   # 21:00 UTC = 17:00 EDT — end boundary
    ("America/New_York", 21,  1, False),  # 21:01 UTC = 17:01 EDT — 1 min after end
    # ── Asia/Kolkata (IST = UTC+5:30) ───────────────────────────────────────
    ("Asia/Kolkata",  3, 30, True),       # 03:30 UTC = 09:00 IST — start boundary
    ("Asia/Kolkata",  3, 29, False),      # 03:29 UTC = 08:59 IST — 1 min before start
    ("Asia/Kolkata", 11, 30, True),       # 11:30 UTC = 17:00 IST — end boundary
    ("Asia/Kolkata", 11, 31, False),      # 11:31 UTC = 17:01 IST — 1 min after end
    # ── Europe/London (BST = UTC+1) ─────────────────────────────────────────
    ("Europe/London",  8,  0, True),      # 08:00 UTC = 09:00 BST — start boundary
    ("Europe/London",  7, 59, False),     # 07:59 UTC = 08:59 BST — 1 min before start
    ("Europe/London", 16,  0, True),      # 16:00 UTC = 17:00 BST — end boundary
    ("Europe/London", 16,  1, False),     # 16:01 UTC = 17:01 BST — 1 min after end
])
def test_active_hours_cross_timezone_border(
    route_tz: str, utc_hour: int, utc_minute: int, expected: bool
):
    ah = ActiveHours(start="09:00", end="17:00", timezone=route_tz)
    assert is_within_active_hours(ah, now=_utc(utc_hour, utc_minute)) is expected


# ---------------------------------------------------------------------------
# find_matching_routes
# ---------------------------------------------------------------------------

def test_find_matching_routes_empty_conditions_matches_all():
    alert = _alert()
    routes = [_route("r1", priority=10), _route("r2", priority=5)]
    result = find_matching_routes(alert, routes)
    assert [r.id for r in result] == ["r1", "r2"]


def test_find_matching_routes_priority_order_preserved():
    alert = _alert()
    # Input already ordered desc by caller (routes_repository.list_all)
    routes = [_route("high", priority=20), _route("low", priority=1)]
    result = find_matching_routes(alert, routes)
    assert result[0].id == "high"


def test_find_matching_routes_filters_non_matching():
    alert = _alert(severity="info")
    routes = [
        _route("r1", conditions={"severity": ["critical"], "service": [], "group": [], "labels": {}}),
        _route("r2"),  # empty conditions → matches all
    ]
    result = find_matching_routes(alert, routes)
    assert [r.id for r in result] == ["r2"]


def test_find_matching_routes_active_hours_filter():
    alert = _alert()
    outside_hours = {"start": "09:00", "end": "10:00"}
    inside_hours = {"start": "00:00", "end": "23:59"}
    routes = [
        _route("outside", active_hours=outside_hours),
        _route("inside", active_hours=inside_hours),
    ]
    now = _now_at(15)  # 15:00 — outside 09:00-10:00
    result = find_matching_routes(alert, routes, now=now)
    assert [r.id for r in result] == ["inside"]


# ---------------------------------------------------------------------------
# is_suppressed
# ---------------------------------------------------------------------------

NOW = datetime.now(timezone.utc)


def test_is_suppressed_no_history():
    assert is_suppressed(None, window_seconds=60, now=NOW) is False


def test_is_suppressed_zero_window():
    assert is_suppressed(NOW - timedelta(seconds=5), window_seconds=0, now=NOW) is False


def test_is_suppressed_within_window():
    last = NOW - timedelta(seconds=30)
    assert is_suppressed(last, window_seconds=60, now=NOW) is True


def test_is_suppressed_outside_window():
    last = NOW - timedelta(seconds=120)
    assert is_suppressed(last, window_seconds=60, now=NOW) is False


def test_is_suppressed_exactly_at_boundary():
    last = NOW - timedelta(seconds=60)
    assert is_suppressed(last, window_seconds=60, now=NOW) is False


def test_is_suppressed_one_second_before_expiry():
    # elapsed = 59s, window = 60s → still inside → suppressed
    last = NOW - timedelta(seconds=59)
    assert is_suppressed(last, window_seconds=60, now=NOW) is True


def test_is_suppressed_one_second_after_expiry():
    # elapsed = 61s, window = 60s → just outside → not suppressed
    last = NOW - timedelta(seconds=61)
    assert is_suppressed(last, window_seconds=60, now=NOW) is False


# ---------------------------------------------------------------------------
# build_evaluation_details
# ---------------------------------------------------------------------------

def test_build_evaluation_details():
    details = build_evaluation_details(total=5, matched=2, suppression_applied=True)
    assert details.total_routes_evaluated == 5
    assert details.routes_matched == 2
    assert details.routes_not_matched == 3
    assert details.suppression_applied is True


def test_build_evaluation_details_no_match():
    details = build_evaluation_details(total=3, matched=0, suppression_applied=False)
    assert details.routes_not_matched == 3
    assert details.suppression_applied is False
