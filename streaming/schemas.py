"""Versioned JSON event contract shared by producer and consumer."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from streaming.config import EVENT_NAMES


EventName = Literal[
    "workspace_created",
    "invite_sent",
    "integration_connected",
    "report_created",
    "report_exported",
    "dashboard_viewed",
    "user_login",
]
EventSource = Literal["web", "mobile", "api"]
DeviceType = Literal["desktop", "mobile", "tablet", "service"]


class ProductEvent(BaseModel):
    """Backward-compatible contract for product event versions 1 and 2."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    event_name: EventName
    event_timestamp: datetime
    event_version: Literal[1, 2]
    properties: Dict[str, Any] = Field(default_factory=dict)
    source: Optional[EventSource] = None
    device_type: Optional[DeviceType] = None

    @field_validator("event_timestamp")
    @classmethod
    def timestamp_must_include_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("event_timestamp must include a timezone")
        return value

    @model_validator(mode="after")
    def version_two_has_context(self) -> "ProductEvent":
        if self.event_version == 2 and (
            self.source is None or self.device_type is None
        ):
            raise ValueError("event_version 2 requires source and device_type")
        return self


def validate_event_name(value: str) -> bool:
    """Convenience helper used by beginner-friendly tests and documentation."""

    return value in EVENT_NAMES
