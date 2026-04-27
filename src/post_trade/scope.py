"""Apply a report selector while preserving venue/order identity."""
from pydantic import BaseModel, ConfigDict

from .events import ExecutionBatch, Key


class ReportScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    venue: Key | None = None
    route: Key | None = None
    symbol: Key | None = None

    def filter(self, batch: ExecutionBatch) -> ExecutionBatch:
        orders = [
            order for order in batch.orders
            if (self.venue is None or self.venue == order.venue)
            and (self.route is None or self.route == order.route)
            and (self.symbol is None or self.symbol == order.symbol)
        ]
        order_keys = {(order.venue, order.order_id) for order in orders}
        fills = [
            fill for fill in batch.fills
            if (self.venue is None or self.venue == fill.venue)
            and ((self.route is None and self.symbol is None) or (fill.venue, fill.order_id) in order_keys)
        ]
        return ExecutionBatch.model_construct(orders=orders, fills=fills)
