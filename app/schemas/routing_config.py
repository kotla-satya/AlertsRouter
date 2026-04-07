import re
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from .alert import SeverityEnum

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class RoutingConfigCondition(BaseModel):
    severity: list[SeverityEnum] = []
    service: list[str] = []  # supports glob patterns e.g. "payment-*"
    group: list[str] = []
    labels: dict[str, str] = {}


class TargetTypeSlack(BaseModel):
    type: Literal["slack"]
    channel: str = Field(min_length=1)


class TargetTypeEmail(BaseModel):
    type: Literal["email"]
    address: EmailStr


class TargetTypePagerDuty(BaseModel):
    type: Literal["pagerduty"]
    service_key: str = Field(min_length=1)


class TargetTypeWebhook(BaseModel):
    type: Literal["webhook"]
    url: str = Field(pattern=r"^https?://")
    headers: dict[str, str] | None = None


RoutingConfigTarget = Annotated[
    TargetTypeSlack | TargetTypeEmail | TargetTypePagerDuty | TargetTypeWebhook,
    Field(discriminator="type"),
]


class ActiveHours(BaseModel):
    start: str
    end: str
    timezone: str = "UTC"

    @field_validator("start", "end")
    @classmethod
    def valid_time(cls, v: str) -> str:
        if not _TIME_RE.match(v):
            raise ValueError("must be HH:MM (00:00–23:59)")
        return v

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, KeyError):
            raise ValueError(f"'{v}' is not a valid IANA timezone (e.g. 'America/New_York', 'UTC')")
        return v

    @model_validator(mode="after")
    def start_ne_end(self) -> "ActiveHours":
        if self.start == self.end:
            raise ValueError("start and end must differ")
        return self


class RoutingConfigCreate(BaseModel):
    id: str = Field(min_length=1)
    conditions: RoutingConfigCondition
    target: RoutingConfigTarget
    priority: int = Field(ge=1)
    suppression_window_seconds: int = Field(default=0, ge=0)
    active_hours: ActiveHours | None = None


class RoutingConfigResponse(RoutingConfigCreate):
    model_config = {"from_attributes": True}


class RouteUpsertResponse(BaseModel):
    id: str
    created: bool  # True = new route, False = replaced existing
