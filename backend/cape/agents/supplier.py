from cape.agents.base import CAPEAgent
from cape.capacity.allocator import CapacityAllocator
from cape.events.schemas import CapacityEvent, DelayEvent, ShipmentEvent


class SupplierAgent(CAPEAgent):
    def _decide(self, tick: int, state: dict) -> list:
        events = []
        allocator = CapacityAllocator(node_id=self.node_id, state=state)
        pending_orders = self.ledger.get_pending_orders(target_node=self.node_id, tick=tick)
        allocation_plan = allocator.solve(pending_orders)
        total_required = sum(int(o.get("quantity_remaining", o["quantity_ordered"])) for o in pending_orders)
        capacity_limit = max(0, int(state.get("capacity_avail", 0)))

        for order in pending_orders:
            order_id = order["order_id"]
            sku_id = order["sku_id"]
            remaining = int(order.get("quantity_remaining", order["quantity_ordered"]))
            allocated = min(int(allocation_plan.get(order_id, 0)), remaining)
            arc = self.ledger.get_arc(from_node=self.node_id, to_node=order["from_node"])

            if allocated > 0:
                shock_delay = max(0, self._scenario_shock(tick, sku_id))
                shipment_event = ShipmentEvent(
                    event_id=self._event_id(
                        tick=tick,
                        event_type="ShipmentEvent",
                        target_node=order["from_node"],
                        sku_id=sku_id,
                        quantity=allocated,
                    ),
                    tick=tick,
                    source_node=self.node_id,
                    target_node=order["from_node"],
                    sku_id=sku_id,
                    quantity=allocated,
                    eta_tick=tick + arc["lead_time_ticks"] + shock_delay,
                    order_ref=order_id,
                    timestamp=self.ledger.get_sim_time(tick),
                )
                self.ledger.record_pipeline_dispatch(
                    order_ref=order_id,
                    from_node=self.node_id,
                    to_node=order["from_node"],
                    sku_id=sku_id,
                    quantity=allocated,
                    dispatched_tick=tick,
                    eta_tick=shipment_event.eta_tick,
                )
                self.ledger.schedule_event(shipment_event, execute_at_tick=shipment_event.eta_tick)
                events.append(shipment_event)

            if allocated < remaining:
                delayed_eta = tick + arc["lead_time_ticks"] + self._estimate_delay(allocated, order) + max(0, self._scenario_shock(tick, sku_id))
                self.ledger.mark_pipeline_delayed(order_ref=order_id, new_eta=delayed_eta)
                delay_event = DelayEvent(
                    event_id=self._event_id(
                        tick=tick,
                        event_type="DelayEvent",
                        target_node=order["from_node"],
                        sku_id=sku_id,
                        quantity=remaining - int(allocated),
                    ),
                    tick=tick,
                    source_node=self.node_id,
                    target_node=order["from_node"],
                    sku_id=sku_id,
                    order_ref=order_id,
                    original_eta=tick + arc["lead_time_ticks"],
                    new_eta=delayed_eta,
                    delay_reason="capacity_overflow_or_scenario_shock",
                    timestamp=self.ledger.get_sim_time(tick),
                )
                events.append(delay_event)

        cap_used = sum(min(int(allocation_plan.get(o["order_id"], 0)), int(o.get("quantity_remaining", o["quantity_ordered"]))) for o in pending_orders)
        cap_total = max(1, int(state["capacity_avail"]))
        util_pct = (cap_used / cap_total * 100) if cap_total > 0 else 0
        events.append(
            CapacityEvent(
                event_id=self._event_id(tick=tick, event_type="CapacityEvent", target_node="SYSTEM", sku_id="ALL", quantity=cap_used),
                tick=tick,
                source_node=self.node_id,
                target_node="SYSTEM",
                sku_id="ALL",
                capacity_used=cap_used,
                capacity_total=max(cap_total, total_required if total_required > 0 else cap_total),
                alert_level="critical" if total_required > capacity_limit or util_pct > 95 else "warning" if util_pct > 80 else "normal",
                timestamp=self.ledger.get_sim_time(tick),
            )
        )
        return events

    def _estimate_delay(self, filled: int, order: dict) -> int:
        ordered = max(1, int(order["quantity_ordered"]))
        shortfall_pct = 1 - (filled / ordered)
        return max(1, int(shortfall_pct * 5))
