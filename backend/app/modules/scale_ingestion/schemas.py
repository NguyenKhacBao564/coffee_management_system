import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator


class ScaleSignalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    sequence: StrictInt = Field(gt=0, le=9_223_372_036_854_775_807)
    observed_at_utc: datetime
    weight_kg: StrictStr = Field(min_length=1, max_length=18)
    vendor_text: StrictStr = Field(max_length=500)
    source: Literal["canxe2015_ui"]

    @field_validator("observed_at_utc", mode="before")
    @classmethod
    def parse_timestamp_string(cls, value: object) -> datetime:
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T.+(?:Z|\+00:00)", value):
            raise ValueError("observed_at_utc phải là chuỗi ISO-8601 có múi giờ UTC")
        try:
            return datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
        except ValueError as exc:
            raise ValueError("observed_at_utc không phải thời điểm ISO-8601 hợp lệ") from exc

    @field_validator("observed_at_utc")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("observed_at_utc phải có múi giờ UTC (Z hoặc +00:00)")
        return value.astimezone(timezone.utc)

    @field_validator("weight_kg")
    @classmethod
    def validate_weight_decimal_string(cls, value: str) -> str:
        if not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,3})?", value):
            raise ValueError("weight_kg phải là chuỗi thập phân chuẩn, tối đa 3 chữ số sau dấu chấm")
        try:
            weight = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("weight_kg không phải số thập phân hợp lệ") from exc
        if not weight.is_finite() or weight < Decimal("1000"):
            raise ValueError("weight_kg phải hữu hạn và tối thiểu 1000 kg")
        if weight > Decimal("99999999999.999"):
            raise ValueError("weight_kg vượt giới hạn NUMERIC(14,3)")
        return value


class ScaleBatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: StrictInt
    agent_id: UUID
    events: list[ScaleSignalIn] = Field(min_length=1, max_length=50)

    @field_validator("schema_version")
    @classmethod
    def require_v1(cls, value: int) -> int:
        if value != 1:
            raise ValueError("schema_version hiện chỉ hỗ trợ 1")
        return value


class ScaleHeartbeatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: StrictInt
    heartbeat_id: UUID
    heartbeat_sequence: StrictInt = Field(gt=0, le=9_223_372_036_854_775_807)
    agent_version: StrictStr | None = Field(default=None, max_length=80)
    process_uptime_seconds: StrictInt | None = Field(default=None, ge=0, le=315_576_000)
    vendor_process_running: StrictBool | None = None
    reader_status: Literal["starting", "ok", "empty", "error", "unavailable"]
    last_successful_read_at_utc: datetime | None = None
    pending_event_count: StrictInt = Field(ge=0, le=1_000_000)
    last_signal_ack_at_utc: datetime | None = None
    last_error_code: StrictStr | None = Field(default=None, max_length=64)

    @field_validator("schema_version")
    @classmethod
    def require_v1(cls, value: int) -> int:
        if value != 1:
            raise ValueError("schema_version hiện chỉ hỗ trợ 1")
        return value

    @field_validator("last_successful_read_at_utc", "last_signal_ack_at_utc", mode="before")
    @classmethod
    def parse_optional_utc_timestamp(cls, value: object) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T.+(?:Z|\+00:00)", value):
            raise ValueError("thời gian phải là chuỗi ISO-8601 UTC có Z hoặc +00:00")
        try:
            return datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
        except ValueError as exc:
            raise ValueError("thời gian ISO-8601 không hợp lệ") from exc

    @field_validator("last_successful_read_at_utc", "last_signal_ack_at_utc")
    @classmethod
    def normalize_optional_utc_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("thời gian phải ở UTC")
        return value.astimezone(timezone.utc)

    @field_validator("agent_version")
    @classmethod
    def validate_agent_version(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value or any(ord(char) < 32 for char in value):
            raise ValueError("agent_version phải là nhãn phiên bản an toàn")
        return value

    @field_validator("last_error_code")
    @classmethod
    def validate_error_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not re.fullmatch(r"[A-Z0-9_]{1,64}", value):
            raise ValueError("last_error_code chỉ được gồm chữ hoa, số và dấu gạch dưới")
        return value
