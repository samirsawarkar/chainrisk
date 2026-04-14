from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class CAPEEvent(BaseModel):
    event_id: str
    event_type: str
    tick: int
    source_node: str
    target_node: str
    sku_id: str
    timestamp: datetime


class OrderEvent(CAPEEvent):
    event_type: Literal["OrderEvent"] = "OrderEvent"
    quantity: int
    priority: int = 5
    reorder_reason: str


class ShipmentEvent(CAPEEvent):
    event_type: Literal["ShipmentEvent"] = "ShipmentEvent"
    quantity: int
    eta_tick: int
    order_ref: str


class DelayEvent(CAPEEvent):
    event_type: Literal["DelayEvent"] = "DelayEvent"
    order_ref: str
    original_eta: int
    new_eta: int
    delay_reason: str


class CapacityEvent(CAPEEvent):
    event_type: Literal["CapacityEvent"] = "CapacityEvent"
    capacity_used: int
    capacity_total: int
    alert_level: str
