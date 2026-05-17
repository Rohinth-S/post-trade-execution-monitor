"""Canonical, JSON-compatible order and fill contracts."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

Key = Annotated[str, Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.:/-]+$")]
Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]
Nonnegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    venue: Key
    order_id: Key

    @field_validator("sent_at", "filled_at", mode="before", check_fields=False)
    @classmethod
    def reject_ambiguous_epoch(cls, value):
        if isinstance(value, str) and "T" not in value and " " not in value:
            raise ValueError("event timestamps must use ISO-8601 date and time with a timezone")
        if not isinstance(value, (str, datetime)):
            raise ValueError("event timestamps must use ISO-8601 date and time with a timezone")
        return value

    @field_validator("sent_at", "filled_at", mode="after", check_fields=False)
    @classmethod
    def canonical_time(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class Order(Event):
    symbol: Key
    route: Key
    side: Literal["buy", "sell"]
    quoted_price_usd: Positive
    quantity: Positive
    sent_at: AwareDatetime


class Receipt(Event):
    fill_id: Key
    quantity: Nonnegative
    executed_price_usd: Positive | None = None
    gas_usd: Nonnegative = 0
    fee_usd: Nonnegative = 0
    filled_at: AwareDatetime
    status: Literal["filled", "failed"] = "filled"

    @model_validator(mode="after")
    def validate_execution(self) -> "Receipt":
        if self.status == "filled" and (self.executed_price_usd is None or self.quantity == 0):
            raise ValueError("filled receipts require a positive quantity and price")
        if self.status == "failed" and (self.quantity or self.executed_price_usd is not None):
            raise ValueError("failed receipts must have zero quantity and no execution price")
        return self


class ExecutionBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    orders: list[Order] = Field(default_factory=list, max_length=10_000)
    fills: list[Receipt] = Field(default_factory=list, max_length=30_000)


class AlertLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    slippage_bps: Nonnegative = 40
    latency_ms: Positive = 1_000
    missing_after_ms: Positive = 5_000
