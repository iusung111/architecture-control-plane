from typing import Generic, Literal, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field


class EnvelopeBase(BaseModel):
    request_id: str
    correlation_id: str = Field(default_factory=lambda: str(uuid4()))
    status: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    retryable: bool
    next_action: str | None = None


class ErrorEnvelope(EnvelopeBase):
    status: Literal["error"] = "error"
    error: ErrorDetail


EnvelopeDataT = TypeVar("EnvelopeDataT", bound=BaseModel)


class DataEnvelope(EnvelopeBase, Generic[EnvelopeDataT]):
    data: EnvelopeDataT


class OkEnvelope(DataEnvelope[EnvelopeDataT], Generic[EnvelopeDataT]):
    status: Literal["ok"] = "ok"


class AcceptedEnvelope(DataEnvelope[EnvelopeDataT], Generic[EnvelopeDataT]):
    status: Literal["accepted"] = "accepted"


def _correlation_id_from_data(data: BaseModel) -> str:
    correlation_id = getattr(data, "cycle_id", None) or getattr(data, "approval_id", None)
    return correlation_id or str(uuid4())


def envelope_ok(data: EnvelopeDataT, request_id: str) -> OkEnvelope[EnvelopeDataT]:
    return OkEnvelope[EnvelopeDataT](
        request_id=request_id,
        correlation_id=_correlation_id_from_data(data),
        data=data,
    )


def envelope_accepted(data: EnvelopeDataT, request_id: str) -> AcceptedEnvelope[EnvelopeDataT]:
    return AcceptedEnvelope[EnvelopeDataT](
        request_id=request_id,
        correlation_id=_correlation_id_from_data(data),
        data=data,
    )


def envelope_error(code: str, message: str, request_id: str, retryable: bool = False) -> ErrorEnvelope:
    return ErrorEnvelope(
        request_id=request_id,
        correlation_id=str(uuid4()),
        error=ErrorDetail(code=code, message=message, retryable=retryable, next_action=None),
    )
