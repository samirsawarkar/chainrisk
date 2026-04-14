from cape.agents.base import CAPEAgent
from cape.events.schemas import OrderEvent


class RetailerAgent(CAPEAgent):
    def _decide(self, tick: int, state: dict) -> list:
        events = []
        customer_demand = self._sample_demand(tick)

        for sku_id, demand in customer_demand.items():
            on_hand = int(state["inventory"].get(sku_id, {}).get("on_hand", 0))
            filled = min(on_hand, demand)
            backlog_new = demand - filled

            perceived_stockout_risk = (backlog_new / demand) if demand > 0 else 0.0
            amplification_factor = float(self.config.get("amplification_factor", 1.35))
            perceived = max(1.0, 0.6 * float(demand) + 0.4 * float(self._previous_demand(sku_id, demand)))
            qty = int(min(perceived * min(amplification_factor + perceived_stockout_risk, 2.5), perceived * 2.5))
            qty = max(1, qty)
            upstream_node = self.ledger.get_upstream_node(self.node_id)
            reason = "backlog_clear" if backlog_new > 0 else "stockout_risk" if on_hand < 5 else "routine"
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

        return events

    def _sample_demand(self, tick: int) -> dict:
        scenario_demand = self.ledger.get_scenario_demand_for_tick(tick)
        if scenario_demand:
            shocks = self.ledger.get_scenario_shock_for_tick(tick)
            adjusted = {}
            for sku_id, demand in scenario_demand.items():
                shock = int(shocks.get(sku_id, 0))
                multiplier = max(0.0, 1.0 + 0.5 * shock)
                adjusted[sku_id] = int(max(0, round(int(demand) * multiplier)))
            return adjusted

        profile = self.config.get("demand_profile", {})
        skus = list(self.config.get("sku_ids", [])) or list(self.config.get("initial_inventory", {}).keys())

        if isinstance(profile, dict) and "by_tick" in profile and tick in profile["by_tick"]:
            by_tick_value = profile["by_tick"][tick]
            if isinstance(by_tick_value, dict):
                return {k: int(max(0, v)) for k, v in by_tick_value.items()}
            if skus:
                return {sku: int(max(0, by_tick_value)) for sku in skus}

        baseline = int(float(profile.get("baseline", self.config.get("avg_demand", 10))))
        volatility = float(profile.get("volatility", 0.0))
        # Deterministic fallback demand when scenario CSV is not provided.
        demand = max(0, int(round(baseline * (1.0 + volatility))))

        if skus:
            return {sku: self._clamp_growth(sku, demand) for sku in skus}
        return {"SKU-DEFAULT": demand}

    def _clamp_growth(self, sku_id: str, demand: int) -> int:
        hist = self.ledger.get_demand_history(self.node_id, sku_id, last_n=1)
        prev = int(hist[-1]) if hist else int(demand)
        if prev > 0 and demand > (prev * 2):
            return int(prev * 2)
        return int(max(0, demand))

    def _previous_demand(self, sku_id: str, fallback: int) -> int:
        hist = self.ledger.get_demand_history(self.node_id, sku_id, last_n=1)
        return int(hist[-1]) if hist else int(fallback)

    def _reorder_point(self, sku_id: str) -> int:
        demand_hist = self.ledger.get_demand_history(self.node_id, sku_id, last_n=5)
        lead_time = self.ledger.get_lead_time(from_node=self.node_id)
        avg_d = (sum(demand_hist) / len(demand_hist)) if demand_hist else float(self.config.get("avg_demand", 10))
        std_d = self._std(demand_hist) if len(demand_hist) > 1 else avg_d * 0.3
        z = 1.65
        return int(avg_d * lead_time + z * std_d * (lead_time ** 0.5))

    def _order_up_to_level(self, sku_id: str, capacity_avail: int) -> int:
        r_point = self._reorder_point(sku_id)
        demand_hist = self.ledger.get_demand_history(self.node_id, sku_id, last_n=3)
        avg_d = (sum(demand_hist) / len(demand_hist)) if demand_hist else float(self.config.get("avg_demand", 10))
        return min(r_point + int(avg_d * 2), int(capacity_avail))

    def _std(self, values: list) -> float:
        n = len(values)
        mean = sum(values) / n
        return (sum((x - mean) ** 2 for x in values) / n) ** 0.5
