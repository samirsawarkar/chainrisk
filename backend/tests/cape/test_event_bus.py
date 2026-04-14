from datetime import datetime, timezone

from cape.events.bus import consume_events, publish_event, schedule_event
from cape.events.schemas import OrderEvent


class DummyRedis:
    def __init__(self):
        self.stream = []
        self.zset = {}

    def xadd(self, key, payload):
        self.stream.append((key, payload))
        return "1-0"

    def zadd(self, key, values):
        self.zset.setdefault(key, {})
        self.zset[key].update(values)

    def zrangebyscore(self, key, min_score, max_score):
        items = self.zset.get(key, {})
        return [k for k, score in items.items() if min_score <= score <= max_score]

    def zrem(self, key, value):
        self.zset.get(key, {}).pop(value, None)


def make_event() -> OrderEvent:
    return OrderEvent(
        event_id="evt-1",
        tick=1,
        source_node="RET-01",
        target_node="DIST-01",
        sku_id="SKU-001",
        quantity=10,
        priority=5,
        reorder_reason="routine",
        timestamp=datetime.now(timezone.utc),
    )


def test_publish_and_consume(monkeypatch):
    import cape.events.bus as bus

    dummy = DummyRedis()
    monkeypatch.setattr(bus, "r", dummy)

    event = make_event()
    message_id = publish_event(event)
    assert message_id == "1-0"
    assert len(dummy.stream) == 1

    schedule_event(event, execute_at_tick=1)
    events = consume_events(current_tick=1)
    assert len(events) == 1
    assert events[0].event_type == "OrderEvent"
