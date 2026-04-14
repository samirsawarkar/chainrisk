from cape.agents.base import CAPEAgent
from cape.capacity.allocator import CapacityAllocator
from cape.events.schemas import CapacityEvent, OrderEvent, ShipmentEvent


class DistributorAgent(CAPEAgent):
    def _decide(self, tick: int, state: dict) -> list:
        events = []
        inventory = state["inventory"]
        capacity_avail = int(state["capacity_avail"])

        pending_orders = self.ledger.get_pending_orders(target_node=self.node_id, tick=tick)
        pending_by_sku: dict[str, int] = {}
        for order in pending_orders:
            pending_by_sku[order["sku_id"]] = pending_by_sku.get(order["sku_id"], 0) + int(order.get("quantity_remaining", order["quantity_ordered"]))
        allocator = CapacityAllocator(node_id=self.node_id, state=state)
        allocation_plan = allocator.solve(pending_orders)

        capacity_consumed = 0
        for order in pending_orders:
            allocated = int(allocation_plan.get(order["order_id"], 0))
            capacity_consumed += int(round(allocated * self.ledger.get_sku_weight(order["sku_id"])))
            if allocated > 0:
                arc = self.ledger.get_arc(from_node=self.node_id, to_node=order["from_node"])
                shock_delay = max(0, self._scenario_shock(tick, order["sku_id"]))
                shipment_event = ShipmentEvent(
                    event_id=self._event_id(
                        tick=tick,
                        event_type="ShipmentEvent",
                        target_node=order["from_node"],
                        sku_id=order["sku_id"],
                        quantity=allocated,
                    ),
                    tick=tick,
                    source_node=self.node_id,
                    target_node=order["from_node"],
                    sku_id=order["sku_id"],
                    quantity=allocated,
                    eta_tick=tick + arc["lead_time_ticks"] + shock_delay,
                    order_ref=order["order_id"],
                    timestamp=self.ledger.get_sim_time(tick),
                )
                self.ledger.record_pipeline_dispatch(
                    order_ref=order["order_id"],
                    from_node=self.node_id,
                    to_node=order["from_node"],
                    sku_id=order["sku_id"],
                    quantity=allocated,
                    dispatched_tick=tick,
                    eta_tick=shipment_event.eta_tick,
                )
                self.ledger.schedule_event(shipment_event, shipment_event.eta_tick)
                events.append(shipment_event)

        for sku_id, inv in inventory.items():
            on_hand = int(inv["on_hand"])
            backlog = int(inv["backlog"])
            net_inv = on_hand - backlog
            reorder_pt = self._reorder_point(sku_id)
            order_up_to = self._order_up_to_level(sku_id, capacity_avail, backlog)
            in_pipeline = self.ledger.get_pipeline_quantity(to_node=self.node_id, sku_id=sku_id, after_tick=tick)
            inventory_position = net_inv + in_pipeline

            observed_downstream = pending_by_sku.get(sku_id, 0)
            qty = 0
            if observed_downstream > 0:
                perceived = self._perceived_demand(sku_id, observed_downstream)
                amplification_factor = float(self.config.get("amplification_factor", 1.4))
                qty = int(min(perceived * amplification_factor, perceived * 2.5))
            elif inventory_position <= reorder_pt:
                qty = max(0, order_up_to - inventory_position)
            if qty > 0:
                upstream_node = self.ledger.get_upstream_node(self.node_id)
                reason = "backlog_clear" if backlog > 0 else "stockout_risk" if on_hand < 5 else "routine"
                order_event = OrderEvent(
                    event_id=self._event_id(tick=tick, event_type="OrderEvent", target_node=upstream_node, sku_id=sku_id, quantity=qty),
                    tick=tick,
                    source_node=self.node_id,
                    target_node=upstream_node,
                    sku_id=sku_id,
                    quantity=qty,
                    priority=1 if reason == "backlog_clear" else 5,
                    reorder_reason=reason,
                    timestamp=self.ledger.get_sim_time(tick),
                )
                self.ledger.schedule_event(order_event, execute_at_tick=tick + 1)
                events.append(order_event)

        cap_total = max(1, capacity_avail)
        util_pct = (capacity_consumed / cap_total * 100) if cap_total > 0 else 0
        events.append(
            CapacityEvent(
                event_id=self._event_id(tick=tick, event_type="CapacityEvent", target_node="SYSTEM", sku_id="ALL", quantity=capacity_consumed),
                tick=tick,
                source_node=self.node_id,
                target_node="SYSTEM",
                sku_id="ALL",
                capacity_used=capacity_consumed,
                capacity_total=cap_total,
                alert_level="critical" if util_pct > 95 else "warning" if util_pct > 80 else "normal",
                timestamp=self.ledger.get_sim_time(tick),
            )
        )
        return events

    def _reorder_point(self, sku_id: str) -> int:
        demand_hist = self.ledger.get_demand_history(self.node_id, sku_id, last_n=5)
        lead_time = self.ledger.get_lead_time(from_node=self.node_id)
        avg_d = (sum(demand_hist) / len(demand_hist)) if demand_hist else float(self.config.get("avg_demand", 10))
        std_d = self._std(demand_hist) if len(demand_hist) > 1 else avg_d * 0.3
        z = 1.65
        return int(avg_d * lead_time + z * std_d * (lead_time ** 0.5))

    def _order_up_to_level(self, sku_id: str, capacity_avail: int, backlog: int = 0) -> int:
        r_point = self._reorder_point(sku_id)
        demand_hist = self.ledger.get_demand_history(self.node_id, sku_id, last_n=3)
        avg_d = (sum(demand_hist) / len(demand_hist)) if demand_hist else float(self.config.get("avg_demand", 10))
        amplification = 1.0 + min(1.0, max(0.0, backlog / max(1.0, avg_d)))
        return max(int(capacity_avail), int((r_point + avg_d * 2) * amplification))

    def _std(self, values: list) -> float:
        n = len(values)
        mean = sum(values) / n
        return (sum((x - mean) ** 2 for x in values) / n) ** 0.5

    def _perceived_demand(self, sku_id: str, current: int) -> float:
        hist = self.ledger.get_demand_history(self.node_id, sku_id, last_n=1)
        previous = float(hist[-1]) if hist else float(current)
        return 0.6 * float(current) + 0.4 * previous
