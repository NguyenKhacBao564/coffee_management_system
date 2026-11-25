import re
import unicodedata
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Role = Literal["admin", "manager", "staff", "drum_operator"]


def normalize_username(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("username")
    @classmethod
    def clean_username(cls, value: str) -> str:
        result = normalize_username(value)
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,63}", result):
            raise ValueError("Tên đăng nhập không hợp lệ")
        return result


class AccountCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    display_name: str = Field(min_length=1, max_length=120)
    role: Role
    facility_ids: list[int] = Field(default_factory=list, max_length=100)
    password: str = Field(min_length=12, max_length=256)

    @field_validator("username")
    @classmethod
    def clean_username(cls, value: str) -> str:
        result = normalize_username(value)
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,63}", result):
            raise ValueError("Tên đăng nhập chỉ dùng chữ thường, số, dấu chấm, gạch dưới hoặc gạch ngang")
        return result

    @field_validator("display_name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        result = value.strip()
        if not result:
            raise ValueError("Tên hiển thị không được để trống")
        return result

    @field_validator("facility_ids")
    @classmethod
    def unique_facilities(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("Cơ sở bị lặp")
        return value

    @field_validator("password")
    @classmethod
    def password_size(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 1024:
            raise ValueError("Mật khẩu quá dài")
        return value


class AccountUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    role: Role
    facility_ids: list[int] = Field(default_factory=list, max_length=100)

    @field_validator("display_name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        result = value.strip()
        if not result:
            raise ValueError("Tên hiển thị không được để trống")
        return result

    @field_validator("facility_ids")
    @classmethod
    def unique_facilities(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("Cơ sở bị lặp")
        return value


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=12, max_length=256)

    @field_validator("new_password")
    @classmethod
    def password_size(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 1024:
            raise ValueError("Mật khẩu quá dài")
        return value


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)

    @field_validator("new_password")
    @classmethod
    def password_size(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 1024:
            raise ValueError("Mật khẩu quá dài")
        return value


class ActiveFacilityRequest(BaseModel):
    facility_id: int


class FacilityOut(BaseModel):
    id: int
    code: str
    name: str

    model_config = ConfigDict(from_attributes=True)


class FacilityCreate(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=2, max_length=120)

    @field_validator("code")
    @classmethod
    def clean_code(cls, value: str) -> str:
        return value.strip().upper()


class FacilityUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    is_active: bool | None = None


class FacilityEmployeeOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class FacilityDrumOut(BaseModel):
    id: int
    drum_code: str
    drum_name: str
    capacity_kg: Decimal | None
    measurement_mode: str
    has_moisture_imbalance: bool
    has_blade_issue: bool
    status: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class FacilityModuleStatus(BaseModel):
    status: str  # "active", "ready", "standby", "unconfigured", "disabled"
    label: str
    details: str


class FacilityDetailOut(BaseModel):
    id: int
    code: str
    name: str
    is_active: bool
    is_demo: bool
    created_at: datetime
    employees: list[FacilityEmployeeOut]
    drums: list[FacilityDrumOut]
    drum_processing_status: FacilityModuleStatus
    camera_status: FacilityModuleStatus
    scale_status: FacilityModuleStatus

    model_config = ConfigDict(from_attributes=True)


class FacilityOverviewItem(BaseModel):
    id: int
    code: str
    name: str
    is_active: bool
    is_demo: bool
    created_at: datetime
    employees_count: int
    drums_count: int
    running_drums_count: int
    cameras_count: int
    scales_count: int
    drum_status: str  # "running", "ready", "no_drums"
    camera_status: str  # "active", "unconfigured"
    scale_status: str  # "active", "unconfigured"

    model_config = ConfigDict(from_attributes=True)


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: Role
    facilities: list[FacilityOut]
    active_facility: FacilityOut | None


class AccountOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: Role
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None
    facilities: list[FacilityOut]


class AccountListOut(BaseModel):
    items: list[AccountOut]
    page: int
    page_size: int
    total: int
