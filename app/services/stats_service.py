from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories import alerts_repository
from ..schemas.stats import RouteStats, StatsResponse


async def get_stats(db: AsyncSession) -> StatsResponse:
    total = await alerts_repository.count_alerts(db)
    total_routed = await alerts_repository.count_alerts(db, is_routed=True)
    total_suppressed = await alerts_repository.count_alerts(db, suppressed=True)
    total_unrouted = total - total_routed - total_suppressed

    by_severity = await alerts_repository.count_by_severity(db)
    by_service = await alerts_repository.count_by_service(db)

    # by_route: requires inspecting routing_result JSON per alert.
    # For routed alerts, matched_routes lists all matching routes.
    # For suppressed alerts, matched_routes is empty — only the primary route
    # (routed_to.route_id) is known.
    all_alerts = await alerts_repository.list_alerts(db, None, None, None, None)
    by_route: dict[str, dict[str, int]] = {}

    def _ensure(route_id: str) -> None:
        if route_id not in by_route:
            by_route[route_id] = {"total_matched": 0, "total_routed": 0, "total_suppressed": 0}

    for alert in all_alerts:
        if not alert.routing_result:
            continue
        rr = alert.routing_result
        routed_to = rr.get("routed_to")
        matched_routes: list[str] = rr.get("matched_routes") or []

        if alert.suppressed and routed_to:
            # matched_routes is empty when suppressed; primary route is still known
            route_id = routed_to["route_id"]
            _ensure(route_id)
            by_route[route_id]["total_matched"] += 1
            by_route[route_id]["total_suppressed"] += 1
        else:
            for route_id in matched_routes:
                _ensure(route_id)
                by_route[route_id]["total_matched"] += 1
            if alert.is_routed and routed_to:
                route_id = routed_to["route_id"]
                _ensure(route_id)
                by_route[route_id]["total_routed"] += 1

    return StatsResponse(
        total_alerts_processed=total,
        total_routed=total_routed,
        total_suppressed=total_suppressed,
        total_unrouted=total_unrouted,
        by_severity=by_severity,
        by_route={k: RouteStats(**v) for k, v in by_route.items()},
        by_service=by_service,
    )
