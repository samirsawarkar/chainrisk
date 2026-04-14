from cape.ledger.adapter import LedgerAdapter


class FakeCursor:
    def __init__(self):
        self.calls = []
        self.last_query = ""

    def execute(self, query, params=None):
        self.last_query = " ".join(query.split())
        self.calls.append((self.last_query, params))

    def fetchone(self):
        if "info_lag_ticks" in self.last_query:
            return (1,)
        if "available_units" in self.last_query:
            return (200,)
        return None

    def fetchall(self):
        if "FROM inventory_state" in self.last_query:
            return [("SKU-001", 50, 3, 0)]
        return []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConn:
    def __init__(self):
        self.cur = FakeCursor()

    def cursor(self):
        return self.cur

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeRedis:
    def __init__(self):
        self.values = {"cape:tick:current": "5"}

    def get(self, key):
        return self.values.get(key)


def test_read_delayed_state(monkeypatch):
    import cape.ledger.adapter as adapter

    monkeypatch.setattr(adapter, "_get_pg_conn", lambda: FakeConn())
    monkeypatch.setattr(adapter, "r", FakeRedis())

    ledger = LedgerAdapter("MFG-01")
    tick = ledger.get_current_tick()
    assert tick == 5

    state = ledger.read_delayed_state(current_tick=tick)
    assert state["node_id"] == "MFG-01"
    assert state["visible_tick"] == 4
    assert state["capacity_avail"] == 200
    assert state["inventory"]["SKU-001"]["on_hand"] == 50
