import json
import os

import redis

from cape.events.schemas import CAPEEvent, CapacityEvent, DelayEvent, OrderEvent, ShipmentEvent

r = redis.Redis(
    host=os.environ.get("CAPE_REDIS_HOST", "localhost"),
    port=int(os.environ.get("CAPE_REDIS_PORT", "6379")),
    db=int(os.environ.get("CAPE_REDIS_DB", "0")),
    decode_responses=True,
)

STREAM_KEY = "cape:events:queue"
SCHEDULED_EVENTS_KEY = "cape:events:scheduled"

_EVENT_CLASS_MAP = {
    "OrderEvent": OrderEvent,
    "ShipmentEvent": ShipmentEvent,
    "DelayEvent": DelayEvent,
    "CapacityEvent": CapacityEvent,
}


def publish_event(event: CAPEEvent) -> str:
    payload = event.model_dump_json()
    message_id = r.xadd(STREAM_KEY, {"payload": payload, "tick": str(event.tick)})
    return message_id


def consume_events(current_tick: int) -> list[CAPEEvent]:
    raw_events = r.zrangebyscore(SCHEDULED_EVENTS_KEY, -1_000_000_000, current_tick)
    events: list[CAPEEvent] = []

    for raw in raw_events:
        data = json.loads(raw)
        event_type = data["event_type"]
        event_class = _EVENT_CLASS_MAP.get(event_type)
        if event_class is None:
            raise ValueError(f"Unsupported CAPE event_type: {event_type}")
        events.append(event_class(**data))
        r.zrem(SCHEDULED_EVENTS_KEY, raw)

    return events


def schedule_event(event: CAPEEvent, execute_at_tick: int):
    r.zadd(SCHEDULED_EVENTS_KEY, {event.model_dump_json(): execute_at_tick})
