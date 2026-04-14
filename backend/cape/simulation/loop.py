import asyncio
import os

import redis

from cape.agents.distributor import DistributorAgent
from cape.agents.manufacturer import ManufacturerAgent
from cape.agents.retailer import RetailerAgent
from cape.agents.supplier import SupplierAgent
from cape.events.bus import consume_events
from cape.ledger.adapter import _get_pg_conn
from cape.simulation.metrics import MetricsEngine
from cape.simulation.state_updater import StateUpdater
from cape.sku_integrity import allowed_skus_from_config, validate_sku_consistency_pg
try:
    from oasis.environment import Environment
except ImportError:
    # oasis>=0.2 no longer exports `Environment`. CAPE only relies on
    # `super().step()` as an async hook, so provide a no-op compatibility base.
    class Environment:
        async def step(self):
            return None

r = redis.Redis(
    host=os.environ.get("CAPE_REDIS_HOST", "localhost"),
    port=int(os.environ.get("CAPE_REDIS_PORT", "6379")),
    db=int(os.environ.get("CAPE_REDIS_DB", "0")),
    decode_responses=True,
)


class CAPEEnvironment(Environment):
    def __init__(self, config: dict, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = config
        self.t_max = int(config["t_max"])
        self.state_updater = StateUpdater()
        self.metrics = MetricsEngine()
        self.agents = self._build_agents()

    def _build_agents(self):
        system_config = self.config.get("system_config", {}) or {}
        sku_ids = [str(item.get("sku_id")) for item in system_config.get("skus", []) if item.get("sku_id")]
        initial_inventory_rows = system_config.get("initial_inventory", []) or []
        inv_map = {}
        for row in initial_inventory_rows:
            node_id = str(row.get("node_id"))
            sku_id = str(row.get("sku_id"))
            inv_map.setdefault(node_id, {})[sku_id] = int(row.get("on_hand", 0))

        type_to_class = {
            "supplier": SupplierAgent,
            "manufacturer": ManufacturerAgent,
            "distributor": DistributorAgent,
            "retailer": RetailerAgent,
        }

        agents = []
        for idx, node in enumerate(system_config.get("nodes", []), start=1):
            node_id = str(node.get("node_id"))
            node_type = str(node.get("node_type", "")).lower()
            agent_cls = type_to_class.get(node_type)
            if not agent_cls:
                continue
            agent_config = {
                "sku_ids": sku_ids,
                "initial_inventory": inv_map.get(node_id, {}),
                "avg_demand": 10,
                "demand_profile": {},
            }
            agents.append(agent_cls(agent_id=f"cape-agent-{idx:02d}", node_id=node_id, config=agent_config))
        return agents

    async def step(self):
        tick = int(r.get("cape:tick:current") or 0)
        due_events = consume_events(current_tick=tick)
        self.state_updater.apply_events(tick, due_events)
        self.state_updater.reset_capacity(tick)
        capacity_events = []
        for agent in self.agents:
            events = await agent.act()
            for event in events:
                if getattr(event, "event_type", "") == "CapacityEvent":
                    capacity_events.append(event)
        if capacity_events:
            self.state_updater.apply_events(tick, capacity_events)
        await super().step()
        metrics = self.metrics.compute(tick)
        self._check_alerts(tick, metrics)
        self.state_updater.flush_to_postgres(tick, metrics)
        r.incr("cape:tick:current")

    def _check_alerts(self, tick: int, metrics: dict):
        alerts: list[str] = []
        for node_id, util in metrics["capacity_utilization"].items():
            if util >= 95.0:
                alerts.append(f"CRITICAL:CAPACITY_SATURATED:{node_id}:{util:.1f}%")
        if metrics["system_backlog"] > self.config["backlog_alert_threshold"]:
            backlog_cost = metrics["system_backlog"] * self.config["avg_stockout_penalty"]
            alerts.append(f"ALERT:BACKLOG_CRITICAL:{metrics['system_backlog']} units:${backlog_cost:,.0f} margin erosion")
        if metrics["instability_index"] > 2.0:
            alerts.append(f"ALERT:BULLWHIP_DETECTED:amplification_ratio={metrics['instability_index']:.2f}")
        if alerts:
            self.metrics.write_alerts(tick, alerts)

    def run(self):
        async def _run():
            r.set("cape:tick:current", 0)
            for _ in range(self.t_max):
                await self.step()

        asyncio.run(_run())
        allowed = allowed_skus_from_config(self.config.get("system_config") or {})
        with _get_pg_conn() as conn:
            bad = validate_sku_consistency_pg(conn, allowed)
        if bad:
            raise ValueError("SKU integrity check failed: " + "; ".join(bad))
