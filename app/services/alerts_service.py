import fnmatch
import zoneinfo
from datetime import datetime, timedelta, timezone

from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.routing_config import RoutingConfig
from ..repositories import alerts_repository, routes_repository
from ..models.alert import Alert
from ..schemas.alert import (
    AlertCreate,
    AlertRoutingResponse,
    AlertsListResponse,
    EvaluationDetails,
    RoutedTo,
)
from ..schemas.routing_config import (
    ActiveHours,
    RoutingConfigCondition,
    RoutingConfigTarget,
)

_target_adapter = TypeAdapter(RoutingConfigTarget)


# ---------------------------------------------------------------------------
# Pure functions — no DB, fully unit-testable
# ---------------------------------------------------------------------------

def match_conditions(alert: AlertCreate, conditions: RoutingConfigCondition) -> bool:
    """Return True if the alert satisfies all non-empty condition fields."""
    if conditions.severity and alert.severity not in conditions.severity:
        return False

    if conditions.service:
        if not any(fnmatch.fnmatch(alert.service, pattern) for pattern in conditions.service):
            return False

    if conditions.group and alert.group not in conditions.group:
        return False

    # Every k/v in conditions.labels must exist in alert.labels (conditions.labels ⊆ alert.labels)
    for key, value in conditions.labels.items():
        if alert.labels.get(key) != value:
            return False

    return True


def is_within_active_hours(
    active_hours: ActiveHours | None,
    now: datetime | None = None,
) -> bool:
    """Return True if now falls within the active_hours window (or active_hours is None)."""
    if active_hours is None:
        return True

    if now is None:
        now = datetime.now(timezone.utc)

    tz = zoneinfo.ZoneInfo(active_hours.timezone)
    local_now = now.astimezone(tz)
    current = local_now.strftime("%H:%M")
    start, end = active_hours.start, active_hours.end

    if start <= end:
        return start <= current <= end
    else:  # overnight window e.g. 22:00–06:00
        return current >= start or current <= end


def find_matching_routes(
    alert: AlertCreate,
    routes: list[RoutingConfig],
    now: datetime | None = None,
) -> list[RoutingConfig]:
    """Return routes that match the alert, preserving priority-desc order."""
    matched = []
    for route in routes:
        conditions = RoutingConfigCondition.model_validate(route.conditions)
        active_hours = ActiveHours.model_validate(route.active_hours) if route.active_hours else None
        if match_conditions(alert, conditions) and is_within_active_hours(active_hours, now):
            matched.append(route)
    return matched


def is_suppressed(
    last_routed_at: datetime | None,
    window_seconds: int,
    now: datetime | None = None,
) -> bool:
    """Return True if the suppression window is still active."""
    if last_routed_at is None or window_seconds == 0:
        return False
    if now is None:
        now = datetime.now(timezone.utc)
    # SQLite returns tz-naive datetimes; treat them as UTC
    if last_routed_at.tzinfo is None:
        last_routed_at = last_routed_at.replace(tzinfo=timezone.utc)
    return (now - last_routed_at) < timedelta(seconds=window_seconds)


def build_evaluation_details(
    total: int,
    matched: int,
    suppression_applied: bool,
) -> EvaluationDetails:
    return EvaluationDetails(
        total_routes_evaluated=total,
        routes_matched=matched,
        routes_not_matched=total - matched,
        suppression_applied=suppression_applied,
    )


# ---------------------------------------------------------------------------
# DB orchestrator
# check for matching routes
# if no match, return immediately
# if match, check for suppression
# if suppressed, return immediately
# if not suppressed, update suppression record and return

# ---------------------------------------------------------------------------

async def route_alert(db: AsyncSession, body: AlertCreate, dry_run: bool = False) -> AlertRoutingResponse:
    now = datetime.now(timezone.utc)

    if not dry_run: #Note: upserting alert to handle alert being submitted multiple times
        await alerts_repository.upsert_alert(db, body.model_dump())

    all_routes = await routes_repository.list_all(db)
    matched = find_matching_routes(body, all_routes, now)

    if not matched:
        response = AlertRoutingResponse(
            alert_id=body.id,
            routed_to=None,
            suppressed=False,
            matched_routes=[],
            evaluation_details=build_evaluation_details(len(all_routes), 0, False),
        )
    else:
        # matched routes are ordered by priority desc
        primary = matched[0]
        routed_to = RoutedTo(
            route_id=primary.id,
            target=_target_adapter.validate_python(primary.target),
        )
        suppression_rec = await alerts_repository.get_suppression(db, primary.id, body.service)
        suppressed = is_suppressed(suppression_rec.last_routed_at if suppression_rec else None,
                                   primary.suppression_window_seconds, now)

        if suppressed:
            response = AlertRoutingResponse(
                alert_id=body.id,
                routed_to=routed_to,
                suppressed=True,
                suppression_reason=(
                    f"Alert for service '{body.service}' suppressed on route '{primary.id}' "
                    f"for {primary.suppression_window_seconds}s"
                ),
                matched_routes=[r.id for r in matched],
                evaluation_details=build_evaluation_details(len(all_routes), len(matched), True),
            )
        else:
            if not dry_run:
                await alerts_repository.upsert_suppression(db, primary.id, body.service, now)
            response = AlertRoutingResponse(
                alert_id=body.id,
                routed_to=routed_to,
                suppressed=False,
                matched_routes=[r.id for r in matched],
                evaluation_details=build_evaluation_details(len(all_routes), len(matched), False),
            )

    if not dry_run:
        await alerts_repository.update_routing_result(
            db,
            body.id,
            routing_result=response.model_dump(mode="json"),
            suppressed=response.suppressed,
            is_routed=response.routed_to is not None and not response.suppressed,
        )
    return response


async def dry_run_route_alert(db: AsyncSession, body: AlertCreate) -> AlertRoutingResponse:
    return await route_alert(db, body, dry_run=True)


def _response_from_alert(alert: Alert) -> AlertRoutingResponse:
    return AlertRoutingResponse.model_validate(alert.routing_result)


async def get_alert_response(db: AsyncSession, alert_id: str) -> AlertRoutingResponse | None:
    alert = await alerts_repository.get_alert_by_id(db, alert_id)
    if alert is None or alert.routing_result is None:
        return None
    return _response_from_alert(alert)


async def list_alert_responses(
    db: AsyncSession,
    service: str | None,
    severity: str | None,
    routed: bool | None,
    suppressed: bool | None,
) -> AlertsListResponse:
    alerts = await alerts_repository.list_alerts(db, service, severity, routed, suppressed)
    items = [_response_from_alert(a) for a in alerts if a.routing_result is not None]
    return AlertsListResponse(alerts=items, total=len(items))
