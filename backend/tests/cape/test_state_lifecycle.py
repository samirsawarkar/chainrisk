import asyncio


def test_step_order(monkeypatch):
    import cape.simulation.loop as loop_mod

    calls = []

    class DummyRedis:
        def __init__(self):
            self.tick = 0

        def get(self, key):
            return str(self.tick)

        def set(self, key, value):
            self.tick = int(value)

        def incr(self, key):
            self.tick += 1

    class DummyUpdater:
        def apply_events(self, tick, events):
            calls.append("apply_events")

        def reset_capacity(self, tick):
            calls.append("reset_capacity")

        def flush_to_postgres(self, tick, metrics):
            calls.append("flush_to_postgres")

    class DummyMetrics:
        def compute(self, tick):
            calls.append("compute")
            return {
                "capacity_utilization": {},
                "system_backlog": 0,
                "instability_index": 1.0,
                "total_holding_cost": 0.0,
                "total_stockout_cost": 0.0,
                "total_transport_cost": 0.0,
                "net_margin_impact": 0.0,
            }

        def write_alerts(self, tick, alerts):
            calls.append("write_alerts")

    async def fake_super_step(self):
        calls.append("super_step")

    monkeypatch.setattr(loop_mod, "r", DummyRedis())
    monkeypatch.setattr(loop_mod, "consume_events", lambda current_tick: [])
    monkeypatch.setattr(loop_mod.CAPEEnvironment, "_check_alerts", lambda self, tick, metrics: calls.append("check_alerts"))
    monkeypatch.setattr(loop_mod.Environment, "step", fake_super_step)

    env = loop_mod.CAPEEnvironment(config={"t_max": 1, "backlog_alert_threshold": 100, "avg_stockout_penalty": 1})
    env.state_updater = DummyUpdater()
    env.metrics = DummyMetrics()

    asyncio.run(env.step())

    assert calls == [
        "apply_events",
        "reset_capacity",
        "super_step",
        "compute",
        "check_alerts",
        "flush_to_postgres",
    ]
