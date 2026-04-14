from cape.capacity.allocator import CapacityAllocator


def test_allocator_greedy(monkeypatch):
    alloc = CapacityAllocator(node_id="SUP-01", state={"capacity_avail": 10})

    monkeypatch.setattr(alloc, "_get_margin", lambda sku: {"A": 5.0, "B": 2.0}[sku])
    monkeypatch.setattr(alloc, "_get_weight", lambda sku: {"A": 1.0, "B": 1.0}[sku])

    plan = alloc.solve(
        [
            {"order_id": "o1", "sku_id": "A", "quantity_ordered": 8, "priority": 5},
            {"order_id": "o2", "sku_id": "B", "quantity_ordered": 8, "priority": 5},
        ]
    )

    assert plan["o1"] == 8
    assert plan["o2"] == 2
