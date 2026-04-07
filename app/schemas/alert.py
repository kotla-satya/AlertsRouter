from typing import Literal

from pydantic import AwareDatetime, BaseModel

SeverityEnum = Literal["critical", "warning", "info"]


class AlertCreate(BaseModel):
    id: str
    severity: SeverityEnum
    service: str
    group: str
    description: str | None = None
    timestamp: AwareDatetime
    labels: dict[str, str] = {}


class AlertResponse(AlertCreate):
    created_at: AwareDatetime
    updated_at: AwareDatetime

    model_config = {"from_attributes": True}


# --- Alert routing response schemas ---

# Import here to avoid circular imports at module level
from .routing_config import RoutingConfigTarget  # noqa: E402


class RoutedTo(BaseModel):
    route_id: str
    target: RoutingConfigTarget


class EvaluationDetails(BaseModel):
    total_routes_evaluated: int
    routes_matched: int
    routes_not_matched: int
    suppression_applied: bool


class AlertRoutingResponse(BaseModel):
    alert_id: str
    routed_to: RoutedTo | None
    suppressed: bool
    suppression_reason: str | None = None
    matched_routes: list[str]
    evaluation_details: EvaluationDetails


class AlertsListResponse(BaseModel):
    alerts: list[AlertRoutingResponse]
    total: int
