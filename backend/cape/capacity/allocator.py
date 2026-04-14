class CapacityAllocator:
    def __init__(self, node_id: str, state: dict):
        self.node_id = node_id
        self.capacity = float(state["capacity_avail"])

    def solve(self, pending_orders: list[dict]) -> dict:
        if not pending_orders:
            return {}

        enriched = []
        for order in pending_orders:
            margin = self._get_margin(order["sku_id"])
            weight = self._get_weight(order["sku_id"])
            ratio = margin / weight if weight > 0 else 0
            effective_ratio = ratio * (11 - int(order.get("priority", 5))) / 10
            enriched.append({**order, "ratio": effective_ratio, "weight": weight})

        enriched.sort(key=lambda item: item["ratio"], reverse=True)

        remaining_capacity = self.capacity
        plan: dict[str, int] = {}
        for order in enriched:
            remaining_qty = int(order.get("quantity_remaining", order["quantity_ordered"]))
            if order["weight"] > 0:
                cap_bound = int(remaining_capacity / order["weight"])
            else:
                cap_bound = remaining_qty
            max_units = min(remaining_qty, cap_bound)
            max_units = max(0, max_units)
            plan[order["order_id"]] = max_units
            remaining_capacity -= max_units * order["weight"]
            if remaining_capacity <= 0:
                break

        for order in enriched:
            if order["order_id"] not in plan:
                plan[order["order_id"]] = 0

        return plan

    def _get_margin(self, sku_id: str) -> float:
        from cape.ledger.adapter import _get_pg_conn

        with _get_pg_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT unit_margin FROM skus WHERE sku_id = %s", (sku_id,))
            row = cur.fetchone()
        return float(row[0]) if row else 1.0

    def _get_weight(self, sku_id: str) -> float:
        from cape.ledger.adapter import _get_pg_conn

        with _get_pg_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT unit_weight FROM skus WHERE sku_id = %s", (sku_id,))
            row = cur.fetchone()
        return float(row[0]) if row else 1.0
