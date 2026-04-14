def test_check_alerts_writes_flags(monkeypatch):
    import cape.simulation.loop as loop_mod

    captured = {}

    class DummyMetrics:
        def write_alerts(self, tick, alerts):
            captured["tick"] = tick
            captured["alerts"] = alerts

    env = loop_mod.CAPEEnvironment(config={"t_max": 1, "backlog_alert_threshold": 10, "avg_stockout_penalty": 5})
    env.metrics = DummyMetrics()

    env._check_alerts(
        7,
        {
            "capacity_utilization": {"SUP-01": 96.2},
            "system_backlog": 15,
            "instability_index": 2.5,
        },
    )

    assert captured["tick"] == 7
    assert len(captured["alerts"]) == 3
