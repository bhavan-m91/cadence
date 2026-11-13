import uuid
from datetime import date, datetime
from typing import Annotated, Any, Generic, TypeVar

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Envelope(BaseModel, Generic[T]):
    data: T
    meta: dict[str, Any] = Field(default_factory=dict)


class OkOut(BaseModel):
    ok: bool = True


class ErrorField(BaseModel):
    path: str
    rule: str
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorBody


def _strip(v: Any) -> Any:
    return v.strip() if isinstance(v, str) else v


Str = Annotated[str, BeforeValidator(_strip)]
Color = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]


def ok(data: Any, **meta: Any) -> dict:
    return {"data": data, "meta": meta}


__all__ = ["ORM", "Envelope", "OkOut", "ErrorEnvelope", "Str", "Color", "ok", "uuid", "date", "datetime"]
