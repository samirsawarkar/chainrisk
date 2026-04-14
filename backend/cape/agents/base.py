import hashlib
from typing import Any

from cape.events.bus import publish_event
from cape.ledger.adapter import LedgerAdapter
try:
    from oasis.social_agent.agent import SocialAgent
except ImportError:  # pragma: no cover - test environment fallback
    class SocialAgent:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            pass


class CAPEAgent(SocialAgent):
    def __init__(self, agent_id: str, node_id: str, config: dict, *args, **kwargs):
        stable_id = int(hashlib.sha1(str(agent_id).encode("utf-8")).hexdigest()[:8], 16) % 1_000_000
        self.social_agent_id = stable_id
        self.node_id = node_id
        self.config = config
        self.ledger = LedgerAdapter(node_id=node_id)
        self.model = None

    async def act(self) -> list[Any]:
        tick = self.ledger.get_current_tick()
        local_state = self.ledger.read_delayed_state(tick)
        events = self._decide(tick, local_state)
        for event in events:
            publish_event(event)
        return events

    def _decide(self, tick: int, local_state: dict) -> list:
        raise NotImplementedError

    def _event_id(self, tick: int, event_type: str, target_node: str, sku_id: str, quantity: int) -> str:
        raw = f"{self.node_id}|{target_node}|{sku_id}|{event_type}|{tick}|{int(quantity)}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]

    def _scenario_shock(self, tick: int, sku_id: str) -> int:
        shocks = self.ledger.get_scenario_shock_for_tick(tick)
        return int(shocks.get(sku_id, 0))
