from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VisitCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    visit_id: UUID
    facility_id: int = Field(ge=1)
    camera_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    source_mode: Literal["live", "replay"]
    source_ref: str | None = Field(default=None, max_length=240)
    start_media_seconds: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=3)
    end_media_seconds: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=3)
    observed_at_utc: datetime | None = None
    status: Literal["open", "departed", "interrupted", "needs_review", "closed"] = "needs_review"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("observed_at_utc")
    @classmethod
    def require_aware_timestamp(cls, value):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("observed_at_utc must include timezone")
        return value


class PredictionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prediction_id: UUID
    evidence_id: UUID | None = None
    source: Literal["local", "api", "mock"]
    identifier_kind: Literal["tractor_plate", "trailer_plate", "painted_text", "container_id", "unknown"]
    raw_text: str | None = Field(default=None, max_length=2000)
    normalized_text: str | None = Field(default=None, max_length=160)
    visible_text: str | None = Field(default=None, max_length=160)
    reading_status: Literal["readable", "partial", "unreadable", "unknown"]
    model_version: str | None = Field(default=None, max_length=120)
    prompt_version: str | None = Field(default=None, max_length=120)
    score_info: dict[str, Any] = Field(default_factory=dict)
    raw_result: dict[str, Any] = Field(default_factory=dict)


class ConfirmationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["confirmed", "corrected", "unknown", "split_visit", "missed_visit"]
    identifier_kind: Literal["tractor_plate", "trailer_plate", "painted_text", "container_id", "unknown"]
    evidence_id: UUID | None = None
    confirmed_text: str | None = Field(default=None, max_length=160)
    visible_text: str | None = Field(default=None, max_length=160)


class ConfirmationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    decision: ConfirmationDecision
    note: str | None = Field(default=None, max_length=2000)
