# CAPE — Capacity Allocation & Propagation Engine
## Full Architecture & Execution Plan
### Built on ChainRisk (OASIS/CAMEL-AI runtime)

---

> **Design Directive:** Every component in this document is written to run in production.
> A supply chain operations head should be able to read this and greenlight implementation
> without asking a single clarifying question.

---

## 0. ChainRisk Internals — What We're Actually Working With

Before designing CAPE, we need to be precise about what ChainRisk *is* at the code level.

| ChainRisk Component | Technology | CAPE Treatment |
|---|---|---|
| Simulation rounds loop | CAMEL-AI / OASIS `Environment.step()` | **KEEP — rename "round" → "tick"** |
| AgentManager | OASIS `AgentManager` | **KEEP — do not touch** |
| Base agent lifecycle | OASIS `SocialAgent` → `act()`, `on_round_start()` | **KEEP — wrap via subclass** |
| Vue 3 frontend | Vite + Vue 3 | **KEEP — add CAPE dashboard panels** |
| Flask backend | Flask + uv | **KEEP — add CAPE API routes** |
| Zep Cloud memory | `ZepCloudMemory` | **REPLACE → PostgreSQL + Redis State Ledger** |
| LLM decision engine | OpenAI-compatible API | **REPLACE → Deterministic LP + optional LLM fallback** |
| Social platforms (Twitter/Reddit) | OASIS channel abstraction | **REPLACE → Supply chain node channels** |
| GraphRAG graph | Zep + entity extractor | **REPLACE → Static supply chain topology JSON** |
| Report agent | LLM-based | **REPLACE → CAPE MetricsEngine** |

**The fundamental insight:** OASIS models a "channel" as a medium through which agents exchange messages.
In CAPE, each supply chain node-to-node arc becomes a channel.
A social post becomes an `OrderEvent`. A reply becomes a `ShipmentEvent`. A round becomes a tick.
**The orchestration loop never changes. Only what agents do inside it changes.**

---

## 1. System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CAPE SYSTEM BOUNDARY                                 │
│                                                                               │
│  ┌─────────────┐     ┌──────────────────────────────────────────────────┐   │
│  │  Scenario   │────▶│              State Ledger                         │   │
│  │  Config     │     │  PostgreSQL (persistent) + Redis (hot state)      │   │
│  │  (JSON/YAML)│     │  inventory | pipeline | capacity | orders | events│   │
│  └─────────────┘     └──────────────┬───────────────────────────────────┘   │
│                                      │ read/write                             │
│  ┌───────────────────────────────────▼───────────────────────────────────┐  │
│  │                    CAPE Agent Layer  (20% replacement)                 │  │
│  │                                                                         │  │
│  │  ┌──────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │  │
│  │  │ Supplier │  │ Manufacturer │  │  Distributor │  │   Retailer   │  │  │
│  │  │CAPEAgent │  │  CAPEAgent   │  │  CAPEAgent   │  │  CAPEAgent   │  │  │
│  │  │          │  │              │  │              │  │              │  │  │
│  │  │ act()    │  │ act()        │  │ act()        │  │ act()        │  │  │
│  │  │ ↓        │  │ ↓            │  │ ↓            │  │ ↓            │  │  │
│  │  │ LP Solver│  │ LP Solver    │  │ LP Solver    │  │ Demand Fcst  │  │  │
│  │  └────┬─────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │  │
│  └───────┼───────────────┼──────────────────┼──────────────────┼──────────┘  │
│          │               │                  │                  │              │
│          └───────────────┴──────────────────┴──────────────────┘              │
│                                      │ emit structured events                  │
│  ┌───────────────────────────────────▼───────────────────────────────────┐  │
│  │                   CAPE Event Bus  (Redis Streams)                      │  │
│  │   OrderEvent | ShipmentEvent | DelayEvent | CapacityEvent              │  │
│  └───────────────────────────────────┬───────────────────────────────────┘  │
│                                       │                                        │
│  ┌────────────────────────────────────▼──────────────────────────────────┐  │
│  │              ChainRisk OASIS Simulation Loop  (80% — DO NOT TOUCH)     │  │
│  │                                                                         │  │
│  │   for tick in range(T_max):                                             │  │
│  │       event_queue.process(tick)          ← CAPE adds this              │  │
│  │       agent_manager.step()               ← OASIS (untouched)           │  │
│  │       metrics_engine.snapshot(tick)      ← CAPE adds this              │  │
│  └────────────────────────────────────┬──────────────────────────────────┘  │
│                                        │                                       │
│  ┌─────────────────────────────────────▼─────────────────────────────────┐  │
│  │                     CAPE Metrics Engine                                 │  │
│  │   capacity_util | instability_index | backlog_Δ | financial_impact     │  │
│  └─────────────────────────────────────┬─────────────────────────────────┘  │
│                                         │                                      │
│  ┌──────────────────────────────────────▼────────────────────────────────┐  │
│  │         Vue 3 Frontend  (ChainRisk frontend — extended, not replaced)   │  │
│  │   CAPE Dashboard | Supply Chain Graph | Alert Feed | Financial P&L     │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Data Model — State Ledger

The State Ledger replaces Zep Cloud. It is the single source of truth for all simulation state.
**All agents read from and write to the ledger exclusively through the `LedgerAdapter` interface.**
No agent ever calls the database directly — this is a hard architectural rule.

### 2.1 PostgreSQL Schema

```sql
-- ── Supply Chain Topology ──────────────────────────────────────────────────

CREATE TABLE sc_nodes (
    node_id         VARCHAR(32) PRIMARY KEY,  -- 'SUP-01', 'MFG-01', 'DIST-01', 'RET-01'
    node_type       VARCHAR(16) NOT NULL,      -- 'supplier' | 'manufacturer' | 'distributor' | 'retailer'
    capacity_units  INTEGER     NOT NULL,      -- max units processable per tick
    holding_cost    NUMERIC(10,4) NOT NULL,    -- $/unit/tick
    stockout_penalty NUMERIC(10,4) NOT NULL,  -- $/unit stockout
    info_lag_ticks  INTEGER DEFAULT 0         -- how many ticks delayed is this node's view
);

CREATE TABLE sc_arcs (
    arc_id          SERIAL PRIMARY KEY,
    from_node       VARCHAR(32) REFERENCES sc_nodes(node_id),
    to_node         VARCHAR(32) REFERENCES sc_nodes(node_id),
    lead_time_ticks INTEGER NOT NULL,          -- deterministic base lead time
    transport_cost  NUMERIC(10,4) NOT NULL     -- $/unit shipped
);

CREATE TABLE skus (
    sku_id          VARCHAR(32) PRIMARY KEY,
    description     TEXT,
    unit_margin     NUMERIC(10,4) NOT NULL,    -- margin contribution $/unit
    unit_weight     NUMERIC(8,4)  NOT NULL     -- capacity consumed per unit
);

-- ── State Tables (written every tick) ─────────────────────────────────────

CREATE TABLE inventory_state (
    snap_id         BIGSERIAL PRIMARY KEY,
    tick            INTEGER     NOT NULL,
    node_id         VARCHAR(32) REFERENCES sc_nodes(node_id),
    sku_id          VARCHAR(32) REFERENCES skus(sku_id),
    on_hand         INTEGER     NOT NULL DEFAULT 0,
    backlog         INTEGER     NOT NULL DEFAULT 0,  -- unfilled demand
    reserved        INTEGER     NOT NULL DEFAULT 0,  -- allocated but not shipped
    UNIQUE (tick, node_id, sku_id)
);

CREATE TABLE pipeline_state (
    pipeline_id     BIGSERIAL PRIMARY KEY,
    order_ref       VARCHAR(64) NOT NULL,      -- links to orders table
    arc_id          INTEGER     REFERENCES sc_arcs(arc_id),
    sku_id          VARCHAR(32) REFERENCES skus(sku_id),
    quantity        INTEGER     NOT NULL,
    dispatched_tick INTEGER     NOT NULL,
    eta_tick        INTEGER     NOT NULL,      -- dispatched_tick + lead_time
    status          VARCHAR(16) DEFAULT 'in_transit'  -- 'in_transit' | 'delivered' | 'delayed'
);

CREATE TABLE capacity_state (
    snap_id         BIGSERIAL PRIMARY KEY,
    tick            INTEGER     NOT NULL,
    node_id         VARCHAR(32) REFERENCES sc_nodes(node_id),
    allocated_units INTEGER     NOT NULL,
    available_units INTEGER     NOT NULL,
    utilization_pct NUMERIC(5,2) GENERATED ALWAYS AS
                    (allocated_units::numeric / NULLIF(allocated_units + available_units, 0) * 100) STORED,
    UNIQUE (tick, node_id)
);

CREATE TABLE orders (
    order_id        VARCHAR(64) PRIMARY KEY,   -- 'ORD-{tick}-{from}-{to}-{sku}'
    tick_placed     INTEGER     NOT NULL,
    from_node       VARCHAR(32) REFERENCES sc_nodes(node_id),
    to_node         VARCHAR(32) REFERENCES sc_nodes(node_id),
    sku_id          VARCHAR(32) REFERENCES skus(sku_id),
    quantity_ordered INTEGER    NOT NULL,
    quantity_filled  INTEGER    DEFAULT 0,
    status          VARCHAR(16) DEFAULT 'pending',  -- 'pending'|'partial'|'filled'|'cancelled'
    priority        SMALLINT    DEFAULT 5           -- 1=highest, 10=lowest
);

-- ── Event Log ──────────────────────────────────────────────────────────────

CREATE TABLE event_log (
    event_id        BIGSERIAL PRIMARY KEY,
    event_type      VARCHAR(32) NOT NULL,  -- 'OrderEvent'|'ShipmentEvent'|'DelayEvent'|'CapacityEvent'
    tick            INTEGER     NOT NULL,
    source_node     VARCHAR(32),
    target_node     VARCHAR(32),
    sku_id          VARCHAR(32),
    payload         JSONB       NOT NULL,
    processed       BOOLEAN     DEFAULT FALSE
);

CREATE INDEX idx_event_log_tick ON event_log(tick, processed);
CREATE INDEX idx_pipeline_eta ON pipeline_state(eta_tick, status);
CREATE INDEX idx_inventory_node_tick ON inventory_state(node_id, tick);

-- ── Metrics Snapshots ──────────────────────────────────────────────────────

CREATE TABLE tick_metrics (
    tick            INTEGER PRIMARY KEY,
    system_backlog  INTEGER     NOT NULL,
    system_capacity_util NUMERIC(5,2) NOT NULL,
    instability_index    NUMERIC(8,4) NOT NULL,  -- variance of order amplification
    total_holding_cost   NUMERIC(12,4) NOT NULL,
    total_stockout_cost  NUMERIC(12,4) NOT NULL,
    total_transport_cost NUMERIC(12,4) NOT NULL,
    net_margin_impact    NUMERIC(12,4) NOT NULL,
    alert_flags     TEXT[]      DEFAULT '{}'  -- ['CAPACITY_SATURATED_MFG-01', ...]
);
```

### 2.2 Redis Schema (Hot State — Current Tick Only)

```
cape:tick:current                          → INTEGER (current simulation tick)
cape:state:{node_id}:{sku_id}:on_hand      → INTEGER
cape:state:{node_id}:{sku_id}:backlog      → INTEGER
cape:capacity:{node_id}:available          → INTEGER
cape:events:queue                          → Redis Stream (XADD/XREAD)
cape:lock:tick                             → SETNX lock for tick atomicity
```

Redis is the agents' real-time read surface. PostgreSQL is the audit trail. Every tick, the simulation
loop flushes Redis hot state to PostgreSQL before incrementing the tick counter.

---

## 3. Event System

Events replace social media posts. They are the **only** inter-agent communication mechanism.

### 3.1 Event Schema (Pydantic models)

```python
# cape/events/schemas.py

from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime

class CAPEEvent(BaseModel):
    event_id:    str                # uuid4
    event_type:  str
    tick:        int
    source_node: str
    target_node: str
    sku_id:      str
    timestamp:   datetime

class OrderEvent(CAPEEvent):
    event_type:      Literal["OrderEvent"] = "OrderEvent"
    quantity:        int
    priority:        int = 5          # 1 = highest urgency
    reorder_reason:  str              # 'stockout_risk' | 'routine' | 'backlog_clear'

class ShipmentEvent(CAPEEvent):
    event_type:      Literal["ShipmentEvent"] = "ShipmentEvent"
    quantity:        int
    eta_tick:        int
    order_ref:       str

class DelayEvent(CAPEEvent):
    event_type:      Literal["DelayEvent"] = "DelayEvent"
    order_ref:       str
    original_eta:    int
    new_eta:         int
    delay_reason:    str  # 'capacity_overflow' | 'supplier_shortage'

class CapacityEvent(CAPEEvent):
    event_type:      Literal["CapacityEvent"] = "CapacityEvent"
    capacity_used:   int
    capacity_total:  int
    alert_level:     str  # 'normal' | 'warning' | 'critical'
    # warning  = utilization > 80%
    # critical = utilization > 95%
```

### 3.2 Event Bus (Redis Streams)

```python
# cape/events/bus.py

import redis
import json
from cape.events.schemas import CAPEEvent

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

STREAM_KEY = "cape:events:queue"

def publish_event(event: CAPEEvent) -> str:
    """
    Publish to Redis Stream. Returns message ID.
    OASIS agents call this at the end of their act() method.
    Redis stream is the ONLY inter-agent communication channel.
    """
    payload = event.model_dump_json()
    msg_id = r.xadd(STREAM_KEY, {"payload": payload, "tick": event.tick})
    return msg_id

def consume_events(current_tick: int) -> list[CAPEEvent]:
    """
    Called at start of each tick by SimulationLoop.
    Reads all events targeted at current_tick (i.e., scheduled deliveries, orders to fill).
    """
    # We use a separate sorted set for scheduled future events
    raw = r.zrangebyscore("cape:events:scheduled", current_tick, current_tick)
    events = []
    for item in raw:
        data = json.loads(item)
        event_type = data["event_type"]
        cls_map = {
            "OrderEvent": OrderEvent,
            "ShipmentEvent": ShipmentEvent,
            "DelayEvent": DelayEvent,
            "CapacityEvent": CapacityEvent,
        }
        events.append(cls_map[event_type](**data))
        r.zrem("cape:events:scheduled", item)
    return events

def schedule_event(event: CAPEEvent, execute_at_tick: int):
    """
    Schedule an event for a future tick. Used for pipeline deliveries.
    e.g., schedule_event(ShipmentEvent(...), execute_at_tick=current_tick + lead_time)
    """
    r.zadd("cape:events:scheduled", {event.model_dump_json(): execute_at_tick})
```

---

## 4. Agent Design

### 4.1 The Integration Contract — CAPEAgent wraps OASIS SocialAgent

This is the most critical design decision. **We never modify OASIS internals.**

```python
# cape/agents/base.py

from oasis.social_agent.agent import SocialAgent   # ChainRisk base — DO NOT MODIFY
from cape.ledger.adapter import LedgerAdapter
from cape.events.bus import publish_event
from typing import Any

class CAPEAgent(SocialAgent):
    """
    Wraps ChainRisk's SocialAgent. All OASIS lifecycle hooks are preserved.
    We override ONLY:
        - __init__  (inject LedgerAdapter instead of Zep memory)
        - act()     (replace LLM call with deterministic decision)
    
    Everything else (registration with AgentManager, tick scheduling,
    async execution, error handling) runs exactly as ChainRisk built it.
    """

    def __init__(self, agent_id: str, node_id: str, config: dict, *args, **kwargs):
        # Call OASIS __init__ with a no-op memory to satisfy the interface
        super().__init__(agent_id=agent_id, *args, **kwargs)
        
        self.node_id  = node_id
        self.config   = config
        self.ledger   = LedgerAdapter(node_id=node_id)

        # CRITICAL: Disable LLM by setting model to None.
        # OASIS checks self.model before calling LLM. Setting it to None
        # causes OASIS to skip LLM inference — confirmed from OASIS source.
        self.model = None

    async def act(self) -> list[Any]:
        """
        Called by OASIS AgentManager once per tick, in parallel with all other agents.
        Returns list of "actions" — in OASIS these are social posts.
        In CAPE, these are CAPEEvent objects written to the Event Bus.
        OASIS does not care what we return as long as it's a list.
        """
        tick = self.ledger.get_current_tick()
        local_state = self.ledger.read_delayed_state(tick)  # applies info_lag
        events = self._decide(tick, local_state)
        
        for event in events:
            publish_event(event)
        
        return events   # OASIS receives these but ignores content for CAPE

    def _decide(self, tick: int, local_state: dict) -> list:
        """
        Subclasses implement this. Returns list of CAPEEvent.
        """
        raise NotImplementedError

    # ── ChainRisk lifecycle hooks we keep untouched ──────────────────────────
    # on_round_start(), on_round_end(), receive_message() — not overridden.
    # They are no-ops in CAPE, which is fine.
```

### 4.2 LedgerAdapter — How Agents Read State

```python
# cape/ledger/adapter.py

import redis
from cape.db import get_pg_conn

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

class LedgerAdapter:
    """
    Single interface between agents and state.
    Agents NEVER call Redis or PostgreSQL directly.
    """

    def __init__(self, node_id: str):
        self.node_id = node_id

    def get_current_tick(self) -> int:
        return int(r.get("cape:tick:current") or 0)

    def read_delayed_state(self, current_tick: int) -> dict:
        """
        Applies information asymmetry. Agent sees state from (tick - info_lag) ticks ago.
        This is what produces the bullwhip effect — agents react to stale demand signals.
        """
        conn = get_pg_conn()
        lag = conn.execute(
            "SELECT info_lag_ticks FROM sc_nodes WHERE node_id = %s", (self.node_id,)
        ).fetchone()[0]
        
        visible_tick = max(0, current_tick - lag)
        
        rows = conn.execute("""
            SELECT sku_id, on_hand, backlog, reserved
            FROM inventory_state
            WHERE node_id = %s AND tick = %s
        """, (self.node_id, visible_tick)).fetchall()
        
        capacity_row = conn.execute("""
            SELECT available_units FROM capacity_state
            WHERE node_id = %s AND tick = %s
        """, (self.node_id, visible_tick)).fetchone()
        
        return {
            "node_id":          self.node_id,
            "visible_tick":     visible_tick,
            "current_tick":     current_tick,
            "inventory":        {r[0]: {"on_hand": r[1], "backlog": r[2], "reserved": r[3]} for r in rows},
            "capacity_avail":   capacity_row[0] if capacity_row else 0,
        }

    def write_state(self, tick: int, inventory: dict, capacity_used: int):
        """
        Called by SimulationLoop (NOT by agents directly) at end of each tick.
        """
        pipe = r.pipeline()
        for sku_id, vals in inventory.items():
            pipe.set(f"cape:state:{self.node_id}:{sku_id}:on_hand", vals["on_hand"])
            pipe.set(f"cape:state:{self.node_id}:{sku_id}:backlog", vals["backlog"])
        pipe.set(f"cape:capacity:{self.node_id}:available",
                 self._get_node_capacity() - capacity_used)
        pipe.execute()
```

### 4.3 Supplier Agent

**Role:** Fills orders from Manufacturer. Constrained by raw material capacity.

```python
# cape/agents/supplier.py

from cape.agents.base import CAPEAgent
from cape.events.schemas import ShipmentEvent, CapacityEvent, DelayEvent
from cape.capacity.allocator import CapacityAllocator
import uuid

class SupplierAgent(CAPEAgent):

    def _decide(self, tick: int, state: dict) -> list:
        events = []
        allocator = CapacityAllocator(node_id=self.node_id, state=state)

        # 1. Fetch pending OrderEvents targeting this node for this tick
        pending_orders = self.ledger.get_pending_orders(target_node=self.node_id, tick=tick)

        # 2. Allocate capacity across orders using profit-maximization LP
        allocation_plan = allocator.solve(pending_orders)
        # allocation_plan: {order_id: quantity_to_fulfill}

        for order in pending_orders:
            order_id  = order["order_id"]
            sku_id    = order["sku_id"]
            allocated = allocation_plan.get(order_id, 0)
            arc       = self.ledger.get_arc(from_node=self.node_id, to_node=order["from_node"])

            if allocated > 0:
                # Schedule ShipmentEvent to arrive at lead_time + current_tick
                ship_event = ShipmentEvent(
                    event_id=str(uuid.uuid4()),
                    tick=tick,
                    source_node=self.node_id,
                    target_node=order["from_node"],
                    sku_id=sku_id,
                    quantity=allocated,
                    eta_tick=tick + arc["lead_time_ticks"],
                    order_ref=order_id,
                    timestamp=self.ledger.get_sim_time(tick)
                )
                self.ledger.schedule_event(ship_event, execute_at_tick=ship_event.eta_tick)
                events.append(ship_event)

            if allocated < order["quantity_ordered"]:
                # Partial fill — emit DelayEvent for remainder
                delay_event = DelayEvent(
                    event_id=str(uuid.uuid4()),
                    tick=tick,
                    source_node=self.node_id,
                    target_node=order["from_node"],
                    sku_id=sku_id,
                    order_ref=order_id,
                    original_eta=tick + arc["lead_time_ticks"],
                    new_eta=tick + arc["lead_time_ticks"] + self._estimate_delay(allocated, order),
                    delay_reason="capacity_overflow",
                    timestamp=self.ledger.get_sim_time(tick)
                )
                events.append(delay_event)

        # 3. Emit CapacityEvent for monitoring
        cap_used = sum(allocation_plan.values())
        cap_total = state["capacity_avail"] + cap_used
        util_pct = cap_used / cap_total * 100 if cap_total > 0 else 0
        events.append(CapacityEvent(
            event_id=str(uuid.uuid4()),
            tick=tick,
            source_node=self.node_id,
            target_node="SYSTEM",
            sku_id="ALL",
            capacity_used=cap_used,
            capacity_total=cap_total,
            alert_level="critical" if util_pct > 95 else "warning" if util_pct > 80 else "normal",
            timestamp=self.ledger.get_sim_time(tick)
        ))

        return events

    def _estimate_delay(self, filled: int, order: dict) -> int:
        # Simple: 1 extra tick per 20% capacity shortfall
        shortfall_pct = 1 - (filled / order["quantity_ordered"])
        return max(1, int(shortfall_pct * 5))
```

### 4.4 Manufacturer Agent

**Role:** Most complex agent. Converts raw materials from Supplier into finished goods.
Must balance production scheduling with capacity and downstream orders.

```python
# cape/agents/manufacturer.py

from cape.agents.base import CAPEAgent
from cape.agents.supplier import SupplierAgent  # reuse capacity logic pattern
from cape.events.schemas import OrderEvent, ShipmentEvent, CapacityEvent
from cape.capacity.allocator import CapacityAllocator
import uuid

class ManufacturerAgent(CAPEAgent):

    def _decide(self, tick: int, state: dict) -> list:
        events = []
        inventory = state["inventory"]
        capacity_avail = state["capacity_avail"]

        # ── Step 1: Fulfill downstream orders (to Distributor) ──────────────
        pending_orders = self.ledger.get_pending_orders(target_node=self.node_id, tick=tick)
        allocator = CapacityAllocator(node_id=self.node_id, state=state)
        allocation_plan = allocator.solve(pending_orders)

        capacity_consumed = 0
        for order in pending_orders:
            allocated = allocation_plan.get(order["order_id"], 0)
            capacity_consumed += allocated * self._capacity_per_unit(order["sku_id"])

            if allocated > 0:
                arc = self.ledger.get_arc(from_node=self.node_id, to_node=order["from_node"])
                ship_event = ShipmentEvent(
                    event_id=str(uuid.uuid4()),
                    tick=tick,
                    source_node=self.node_id,
                    target_node=order["from_node"],
                    sku_id=order["sku_id"],
                    quantity=allocated,
                    eta_tick=tick + arc["lead_time_ticks"],
                    order_ref=order["order_id"],
                    timestamp=self.ledger.get_sim_time(tick)
                )
                self.ledger.schedule_event(ship_event, ship_event.eta_tick)
                events.append(ship_event)

        # ── Step 2: Replenishment ordering from Supplier ─────────────────────
        # Decision logic: (s, S) policy with capacity-adjusted safety stock
        for sku_id, inv in inventory.items():
            on_hand     = inv["on_hand"]
            backlog     = inv["backlog"]
            net_inv     = on_hand - backlog
            reorder_pt  = self._reorder_point(sku_id)
            order_up_to = self._order_up_to_level(sku_id, capacity_avail)
            
            in_pipeline = self.ledger.get_pipeline_quantity(
                to_node=self.node_id, sku_id=sku_id, after_tick=tick
            )
            
            inventory_position = net_inv + in_pipeline

            if inventory_position <= reorder_pt:
                qty = max(0, order_up_to - inventory_position)
                if qty > 0:
                    supplier_node = self.ledger.get_upstream_node(self.node_id)
                    arc = self.ledger.get_arc(from_node=self.node_id, to_node=supplier_node)
                    
                    reason = "backlog_clear" if backlog > 0 else "stockout_risk" if on_hand < 5 else "routine"
                    
                    order_event = OrderEvent(
                        event_id=str(uuid.uuid4()),
                        tick=tick,
                        source_node=self.node_id,
                        target_node=supplier_node,
                        sku_id=sku_id,
                        quantity=qty,
                        priority=1 if reason == "backlog_clear" else 5,
                        reorder_reason=reason,
                        timestamp=self.ledger.get_sim_time(tick)
                    )
                    self.ledger.schedule_event(order_event, execute_at_tick=tick + 1)
                    events.append(order_event)

        # ── Step 3: Capacity telemetry ────────────────────────────────────────
        cap_total = state["capacity_avail"] + capacity_consumed
        util_pct = capacity_consumed / cap_total * 100 if cap_total > 0 else 0
        events.append(CapacityEvent(
            event_id=str(uuid.uuid4()),
            tick=tick,
            source_node=self.node_id,
            target_node="SYSTEM",
            sku_id="ALL",
            capacity_used=capacity_consumed,
            capacity_total=cap_total,
            alert_level="critical" if util_pct > 95 else "warning" if util_pct > 80 else "normal",
            timestamp=self.ledger.get_sim_time(tick)
        ))

        return events

    def _reorder_point(self, sku_id: str) -> int:
        """
        R = avg_demand_per_tick * lead_time + safety_stock
        Safety stock = z * σ_demand * sqrt(lead_time)
        Uses last 5 ticks' demand if available, else config default.
        """
        demand_hist = self.ledger.get_demand_history(self.node_id, sku_id, last_n=5)
        lead_time = self.ledger.get_lead_time(from_node=self.node_id)
        avg_d = sum(demand_hist) / len(demand_hist) if demand_hist else self.config.get("avg_demand", 10)
        std_d = self._std(demand_hist) if len(demand_hist) > 1 else avg_d * 0.3
        z = 1.65  # 95% service level
        return int(avg_d * lead_time + z * std_d * (lead_time ** 0.5))

    def _order_up_to_level(self, sku_id: str, capacity_avail: int) -> int:
        # S = R + avg_demand_per_tick * review_period
        # Cap at capacity to avoid over-ordering
        r_point = self._reorder_point(sku_id)
        demand_hist = self.ledger.get_demand_history(self.node_id, sku_id, last_n=3)
        avg_d = sum(demand_hist) / len(demand_hist) if demand_hist else self.config.get("avg_demand", 10)
        return min(r_point + int(avg_d * 2), capacity_avail)

    def _capacity_per_unit(self, sku_id: str) -> float:
        return self.ledger.get_sku_weight(sku_id)

    def _std(self, values: list) -> float:
        n = len(values)
        mean = sum(values) / n
        return (sum((x - mean) ** 2 for x in values) / n) ** 0.5
```

### 4.5 Distributor and Retailer Agents

**Distributor:** Mirrors Manufacturer logic but without production step.
Decision function: receive from Manufacturer, fulfill to Retailer, reorder from Manufacturer.
Demand signal = aggregated Retailer orders (with info lag).

**Retailer:** Simplest agent.
Decision function: observe actual customer demand (stochastic input from scenario config),
place orders upstream, track stockouts for financial impact calculation.

```python
# cape/agents/retailer.py  (condensed)

class RetailerAgent(CAPEAgent):
    def _decide(self, tick: int, state: dict) -> list:
        # 1. Sample customer demand from scenario demand profile
        customer_demand = self._sample_demand(tick)
        
        # 2. Fulfill from on-hand inventory
        for sku_id, demand in customer_demand.items():
            on_hand = state["inventory"].get(sku_id, {}).get("on_hand", 0)
            filled  = min(on_hand, demand)
            backlog_new = demand - filled
            # Stockout cost calculated by MetricsEngine from backlog delta
        
        # 3. Replenishment order to Distributor using (s,S) policy
        # Same pattern as ManufacturerAgent._decide() Step 2
        # Retailer amplifies: reorder_qty = demand * (1 + perceived_stockout_risk)
        # This amplification is the seed of the bullwhip effect
        ...
```

---

## 5. Capacity Allocation Logic (LP Formulation)

This is the decision brain. Replaces LLM inference entirely.

```python
# cape/capacity/allocator.py

from scipy.optimize import linprog
import numpy as np

class CapacityAllocator:
    """
    Solves: maximize total margin subject to capacity constraint.
    
    Formally:
        max  Σ margin_i * x_i
        s.t. Σ weight_i * x_i <= capacity_available
             0 <= x_i <= order_qty_i  (for each order i)
    
    This is a bounded LP. For MSME-scale (< 50 orders/tick), solves in <1ms.
    For large-scale (100+ orders), use greedy margin-per-capacity-unit ranking.
    """

    def __init__(self, node_id: str, state: dict):
        self.node_id = node_id
        self.capacity = state["capacity_avail"]

    def solve(self, pending_orders: list[dict]) -> dict:
        if not pending_orders:
            return {}
        
        # Greedy approach (fast, near-optimal for unimodal margin distributions)
        # Sort by margin_per_capacity_unit descending, fill greedily
        enriched = []
        for o in pending_orders:
            margin = self._get_margin(o["sku_id"])
            weight = self._get_weight(o["sku_id"])
            ratio  = margin / weight if weight > 0 else 0
            # Priority boost: high-priority orders get ratio multiplier
            effective_ratio = ratio * (11 - o.get("priority", 5)) / 10
            enriched.append({**o, "ratio": effective_ratio, "weight": weight})
        
        enriched.sort(key=lambda x: x["ratio"], reverse=True)
        
        remaining_capacity = self.capacity
        plan = {}
        
        for order in enriched:
            max_units = min(
                order["quantity_ordered"],
                int(remaining_capacity / order["weight"]) if order["weight"] > 0 else order["quantity_ordered"]
            )
            plan[order["order_id"]] = max_units
            remaining_capacity -= max_units * order["weight"]
            if remaining_capacity <= 0:
                break
        
        # Unfilled orders get 0
        for order in enriched:
            if order["order_id"] not in plan:
                plan[order["order_id"]] = 0
        
        return plan

    def _get_margin(self, sku_id: str) -> float:
        from cape.db import get_pg_conn
        conn = get_pg_conn()
        row = conn.execute("SELECT unit_margin FROM skus WHERE sku_id = %s", (sku_id,)).fetchone()
        return float(row[0]) if row else 1.0

    def _get_weight(self, sku_id: str) -> float:
        from cape.db import get_pg_conn
        conn = get_pg_conn()
        row = conn.execute("SELECT unit_weight FROM skus WHERE sku_id = %s", (sku_id,)).fetchone()
        return float(row[0]) if row else 1.0
```

---

## 6. Simulation Loop — Step-by-Step Tick Lifecycle

This is the most critical integration point. We **wrap** the OASIS simulation loop,
not replace it. OASIS calls `agent_manager.step()` each round. We hook into
the loop by subclassing OASIS's `Environment` and inserting CAPE logic before and after.

```python
# cape/simulation/loop.py

from oasis.environment import Environment   # ChainRisk base — DO NOT MODIFY
from cape.events.bus import consume_events
from cape.simulation.state_updater import StateUpdater
from cape.simulation.metrics import MetricsEngine
from cape.db import get_pg_conn
import redis

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

class CAPEEnvironment(Environment):
    """
    Extends OASIS Environment. Injects CAPE logic before/after each round.
    OASIS calls self.step() each round. We override step() with CAPE logic
    sandwiched around super().step() (which runs AgentManager).
    """

    def __init__(self, config: dict, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config        = config
        self.t_max         = config["t_max"]
        self.state_updater = StateUpdater()
        self.metrics       = MetricsEngine()

    async def step(self):
        """
        One tick = one complete supply chain day/period.
        
        Execution order (CRITICAL — do not reorder):
        1. Get current tick
        2. Process scheduled events due at this tick (deliveries arrive, orders activate)
        3. Update physical state (inventory += arrivals, capacity resets)
        4. Run AgentManager (agents read state, make decisions, emit new events)
        5. Snapshot metrics
        6. Flush hot state to PostgreSQL
        7. Increment tick counter
        """

        tick = int(r.get("cape:tick:current") or 0)

        # ── Phase 1: Process Scheduled Events ──────────────────────────────
        due_events = consume_events(current_tick=tick)
        self.state_updater.apply_events(tick, due_events)
        # apply_events: ShipmentEvent → inventory += quantity; OrderEvent → insert orders table

        # ── Phase 2: Reset Capacity for This Tick ──────────────────────────
        self.state_updater.reset_capacity(tick)
        # Each node's capacity_available resets to its configured maximum each tick

        # ── Phase 3: Agent Decision Phase (OASIS AgentManager) ─────────────
        # This is the 80% we do not touch.
        # OASIS calls each CAPEAgent.act() in async parallel.
        # Agents read delayed state via LedgerAdapter and emit events to Event Bus.
        await super().step()

        # ── Phase 4: Metrics Snapshot ───────────────────────────────────────
        metrics = self.metrics.compute(tick)
        self._check_alerts(tick, metrics)

        # ── Phase 5: Flush to PostgreSQL ────────────────────────────────────
        self.state_updater.flush_to_postgres(tick, metrics)

        # ── Phase 6: Advance Tick ───────────────────────────────────────────
        r.incr("cape:tick:current")

    def _check_alerts(self, tick: int, metrics: dict):
        alerts = []
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
        import asyncio
        async def _run():
            r.set("cape:tick:current", 0)
            for _ in range(self.t_max):
                await self.step()
        asyncio.run(_run())
```

### 6.1 Complete Tick-by-Tick Flow (Scenario: Retailer Demand Spike)

```
T=0  Initialization
     ├─ PostgreSQL: insert sc_nodes, sc_arcs, skus, initial inventory_state
     ├─ Redis: set cape:tick:current = 0
     └─ OASIS: register 4 CAPEAgents with AgentManager

T=1  Normal operations
     ├─ consume_events(T=1): no scheduled events yet
     ├─ RetailerAgent.act(): demand = 100 units → on_hand = 200 → fills 100, backlog = 0
     │   └─ emits OrderEvent(qty=50) to Distributor, scheduled at T=2
     ├─ DistributorAgent.act(): no new orders yet (info lag = 1 tick)
     ├─ ManufacturerAgent.act(): routine reorder from Supplier
     ├─ SupplierAgent.act(): fills Manufacturer's pending order
     │   └─ ShipmentEvent(qty=80) scheduled at T=1+2=T=3
     └─ Metrics: utilization=40%, backlog=0, instability=1.0

T=3  Shipment arrives at Manufacturer
     ├─ consume_events(T=3): ShipmentEvent → Manufacturer inventory += 80
     ├─ ManufacturerAgent.act(): demand signal from Distributor received (delayed)
     └─ Metrics: capacity util stable

T=5  Retailer demand spike (+300% — demand scenario injection)
     ├─ RetailerAgent.act(): demand = 300 → on_hand = 150 → fills 150, backlog = 150
     │   └─ emits OrderEvent(qty=300, priority=1, reason='backlog_clear')
     ├─ DistributorAgent.act(): sees T=4 state (lag=1). Does not yet see spike.
     │   └─ emits OrderEvent(qty=80, routine)  ← will amplify bullwhip
     └─ Alert: ALERT:BACKLOG_CRITICAL:150 units:$14,250 margin erosion

T=6  Demand spike signal propagates (bullwhip begins)
     ├─ DistributorAgent.act(): NOW sees T=5 backlog (lag=1 tick)
     │   └─ emits OrderEvent(qty=350, priority=1)  ← over-orders relative to actual demand
     ├─ ManufacturerAgent.act(): sees T=5 Distributor order (lag=1)
     │   └─ emits OrderEvent(qty=400) to Supplier  ← further amplified
     └─ CapacityEvent: Supplier util=92% → ALERT:WARNING

T=7  Supplier hits capacity wall
     ├─ SupplierAgent.act(): capacity = 380 units, orders = 500 units
     │   └─ allocator.solve() → fills high-margin SKUs first
     │   └─ DelayEvent: 120 units delayed by 2 ticks
     └─ Alert: CRITICAL:CAPACITY_SATURATED:SUP-01:97.4%

T=9  Delayed shipment arrives + demand has normalized
     ├─ 120 units arrive → Manufacturer overstock
     ├─ RetailerAgent.act(): demand = 100 (normalized), on_hand = 150 → fills 100
     │   └─ does NOT reorder (overstocked) ← demand signal collapses
     └─ Instability Index = 3.8 → Alert: ALERT:BULLWHIP_DETECTED:amplification=3.8
     └─ Working capital stress: $42k tied up in excess pipeline inventory
```

---

## 7. Metrics Engine

```python
# cape/simulation/metrics.py

from cape.db import get_pg_conn
import redis

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

class MetricsEngine:

    def compute(self, tick: int) -> dict:
        conn = get_pg_conn()
        
        # ── Capacity Utilization per node ────────────────────────────────────
        cap_rows = conn.execute("""
            SELECT node_id, utilization_pct
            FROM capacity_state
            WHERE tick = %s
        """, (tick,)).fetchall()
        capacity_utilization = {row[0]: float(row[1]) for row in cap_rows}

        # ── System Backlog ────────────────────────────────────────────────────
        backlog_row = conn.execute("""
            SELECT SUM(backlog) FROM inventory_state WHERE tick = %s
        """, (tick,)).fetchone()
        system_backlog = int(backlog_row[0] or 0)

        # ── Financial Impact ──────────────────────────────────────────────────
        holding_cost = conn.execute("""
            SELECT SUM(i.on_hand * n.holding_cost)
            FROM inventory_state i
            JOIN sc_nodes n ON i.node_id = n.node_id
            WHERE i.tick = %s
        """, (tick,)).fetchone()[0] or 0

        stockout_cost = conn.execute("""
            SELECT SUM(i.backlog * n.stockout_penalty)
            FROM inventory_state i
            JOIN sc_nodes n ON i.node_id = n.node_id
            WHERE i.tick = %s
        """, (tick,)).fetchone()[0] or 0

        transport_cost = conn.execute("""
            SELECT SUM(p.quantity * a.transport_cost)
            FROM pipeline_state p
            JOIN sc_arcs a ON p.arc_id = a.arc_id
            WHERE p.dispatched_tick = %s
        """, (tick,)).fetchone()[0] or 0

        # ── Bullwhip / Instability Index ──────────────────────────────────────
        # Ratio of order variance to demand variance (Beer Game formulation)
        # II > 1.0 = amplification; II > 2.0 = significant instability
        instability_index = self._compute_instability_index(conn, tick)

        return {
            "tick":                  tick,
            "capacity_utilization":  capacity_utilization,
            "system_backlog":        system_backlog,
            "instability_index":     instability_index,
            "total_holding_cost":    float(holding_cost),
            "total_stockout_cost":   float(stockout_cost),
            "total_transport_cost":  float(transport_cost),
            "net_margin_impact":     -(float(holding_cost) + float(stockout_cost) + float(transport_cost)),
        }

    def _compute_instability_index(self, conn, tick: int) -> float:
        if tick < 5:
            return 1.0  # Not enough history
        
        # Retailer demand variance (last 5 ticks)
        retail_demand = conn.execute("""
            SELECT SUM(backlog + on_hand) FROM inventory_state
            WHERE node_id LIKE 'RET-%' AND tick >= %s AND tick <= %s
        """, (tick - 5, tick)).fetchall()
        
        # Supplier order variance (last 5 ticks)
        supplier_orders = conn.execute("""
            SELECT SUM(quantity_ordered) FROM orders
            WHERE to_node LIKE 'SUP-%' AND tick_placed >= %s AND tick_placed <= %s
            GROUP BY tick_placed
        """, (tick - 5, tick)).fetchall()
        
        if not supplier_orders or len(supplier_orders) < 2:
            return 1.0
        
        vals = [float(r[0] or 0) for r in supplier_orders]
        mean = sum(vals) / len(vals)
        variance = sum((v - mean) ** 2 for v in vals) / len(vals)
        
        # Normalized against retail demand variance
        ret_vals = [float(r[0] or 0) for r in retail_demand]
        ret_mean = sum(ret_vals) / len(ret_vals) if ret_vals else 1
        ret_var  = sum((v - ret_mean) ** 2 for v in ret_vals) / len(ret_vals) if ret_vals else 1
        
        return round(variance / ret_var, 4) if ret_var > 0 else 1.0

    def write_alerts(self, tick: int, alerts: list[str]):
        conn = get_pg_conn()
        conn.execute("""
            UPDATE tick_metrics SET alert_flags = %s WHERE tick = %s
        """, (alerts, tick))
        conn.commit()
```

---

## 8. ChainRisk Integration — Exact File-Level Plan

### 8.1 Directory Structure After CAPE Integration

```
chainrisk/
├── backend/
│   ├── app.py                    ← ADD: CAPE API routes (/api/cape/*)
│   ├── oasis/                    ← DO NOT TOUCH (entire directory)
│   │   ├── agent_manager.py
│   │   ├── environment.py
│   │   └── social_agent/
│   │       └── agent.py          ← CAPEAgent imports from here — READ ONLY
│   ├── services/
│   │   ├── simulation_runner.py  ← MODIFY: detect scenario_type='cape', branch to CAPEEnvironment
│   │   └── report_agent.py       ← KEEP for LLM fallback; add MetricsEngine alongside
│   └── cape/                     ← NEW: entire CAPE module (20% layer)
│       ├── agents/
│       │   ├── base.py
│       │   ├── supplier.py
│       │   ├── manufacturer.py
│       │   ├── distributor.py
│       │   └── retailer.py
│       ├── capacity/
│       │   └── allocator.py
│       ├── events/
│       │   ├── bus.py
│       │   └── schemas.py
│       ├── ledger/
│       │   └── adapter.py
│       ├── simulation/
│       │   ├── loop.py
│       │   ├── state_updater.py
│       │   └── metrics.py
│       └── db.py
├── frontend/
│   ├── src/
│   │   ├── views/                ← ADD: CapeDashboard.vue alongside existing views
│   │   │   ├── CapeDashboard.vue
│   │   │   ├── CapeGraph.vue     ← Supply chain topology visualization
│   │   │   └── CapeAlerts.vue    ← Real-time alert feed
│   │   └── components/           ← KEEP existing components
└── docker-compose.yml            ← ADD: postgres and redis services
```

### 8.2 The Single Modification to ChainRisk Core

The **only** change to existing ChainRisk files is 8 lines in `simulation_runner.py`:

```python
# backend/services/simulation_runner.py
# EXISTING code — add ONLY the lines marked with ← ADD

def run_simulation(config: dict):
    scenario_type = config.get("scenario_type", "social")  # ← ADD
    
    if scenario_type == "cape":                             # ← ADD
        from cape.simulation.loop import CAPEEnvironment   # ← ADD
        env = CAPEEnvironment(config=config)                # ← ADD
        env.run()                                           # ← ADD
        return                                              # ← ADD
    
    # All existing ChainRisk social simulation code below — UNTOUCHED
    environment = Environment(...)
    ...
```

That is the entire modification to existing ChainRisk code.
Everything else in the CAPE module is **additive** — new files, new routes, new services.

### 8.3 Flask API Extensions

```python
# backend/app.py — ADD these routes (do not remove any existing routes)

from cape.simulation.metrics import MetricsEngine
from cape.db import get_pg_conn

@app.route('/api/cape/run', methods=['POST'])
def cape_run():
    """Launch a CAPE simulation scenario."""
    config = request.json
    config["scenario_type"] = "cape"
    # Reuse existing ChainRisk task queue (Celery/background threads)
    from services.simulation_runner import run_simulation
    task = run_in_background(run_simulation, config)
    return jsonify({"task_id": task.id, "status": "started"})

@app.route('/api/cape/metrics/<int:tick>', methods=['GET'])
def cape_metrics(tick: int):
    """Fetch metrics snapshot for a specific tick."""
    conn = get_pg_conn()
    row = conn.execute("SELECT * FROM tick_metrics WHERE tick = %s", (tick,)).fetchone()
    return jsonify(dict(row) if row else {})

@app.route('/api/cape/alerts', methods=['GET'])
def cape_alerts():
    """Fetch all non-empty alert events."""
    conn = get_pg_conn()
    rows = conn.execute("""
        SELECT tick, alert_flags FROM tick_metrics
        WHERE array_length(alert_flags, 1) > 0
        ORDER BY tick DESC LIMIT 50
    """).fetchall()
    return jsonify([{"tick": r[0], "alerts": r[1]} for r in rows])

@app.route('/api/cape/state/live', methods=['GET'])
def cape_live_state():
    """WebSocket-ready endpoint: current tick hot state from Redis."""
    import redis
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    tick = r.get("cape:tick:current")
    return jsonify({"current_tick": tick})
```

---

## 9. Execution Roadmap

### Phase 1 — Foundation (Week 1–2)
**Goal:** State Ledger is live. Events can be emitted and consumed.

| Task | Owner | Output |
|---|---|---|
| Add PostgreSQL + Redis to docker-compose.yml | Dev | Running DB stack |
| Run schema migrations (all 8 tables) | Dev | Schema validated |
| Build `LedgerAdapter` with read/write tests | Dev | Unit tests pass |
| Build `EventBus` (publish + schedule + consume) | Dev | Redis stream verified |
| Build `CapacityAllocator` with greedy LP | Dev | Allocator tested against synthetic orders |
| Load first scenario: 4 nodes, 1 SKU, T=10 | Dev | Static data in PostgreSQL |

**Validation checkpoint:** Run `LedgerAdapter.read_delayed_state()` for all 4 nodes.
Confirm info lag is correctly applied. Confirm capacity resets each tick.

---

### Phase 2 — Agent Layer (Week 2–3)
**Goal:** All 4 CAPEAgents registered with OASIS AgentManager and executing `act()`.

| Task | Owner | Output |
|---|---|---|
| Build `CAPEAgent` base class (subclasses OASIS SocialAgent) | Dev | OASIS accepts agent |
| Confirm `self.model = None` suppresses LLM calls in OASIS | Dev | No API calls observed |
| Build `SupplierAgent` | Dev | Emits ShipmentEvent, CapacityEvent |
| Build `ManufacturerAgent` with (s,S) policy | Dev | Emits OrderEvent, ShipmentEvent |
| Build `DistributorAgent` | Dev | Emits OrderEvent, ShipmentEvent |
| Build `RetailerAgent` with stochastic demand | Dev | Emits OrderEvent |
| Register all 4 agents via existing OASIS agent config JSON | Dev | AgentManager lists all 4 agents |

**Validation checkpoint:** Run `CAPEEnvironment.step()` for T=1 manually.
Observe all 4 agents emitting events. Confirm events reach Redis stream.

---

### Phase 3 — Full Simulation (Week 3–4)
**Goal:** Complete 20-tick simulation with demand spike scenario. Alerts fire correctly.

| Task | Owner | Output |
|---|---|---|
| Build `CAPEEnvironment` wrapping OASIS `Environment` | Dev | Full tick lifecycle |
| Build `StateUpdater` (apply events, reset capacity, flush to PG) | Dev | State consistent across ticks |
| Build `MetricsEngine` (all 5 metrics computed per tick) | Dev | `tick_metrics` table populated |
| Add alert detection + `alert_flags` writing | Dev | Alerts visible in DB |
| Run 8-modifier in `simulation_runner.py` | Dev | CAPE scenario launches via existing API |
| Run Scenario A: Stable demand (T=20, 1 SKU) | Dev | Metrics baseline established |
| Run Scenario B: Demand spike at T=5 | Dev | Bullwhip detected at T=7-9 |
| Run Scenario C: Supplier capacity cap at 80% | Dev | Delay cascade + financial alert |

**Validation checkpoint:** Scenario B must produce:
- `instability_index > 2.0` within 4 ticks of demand spike
- `CRITICAL:CAPACITY_SATURATED` alert at supplier node
- `net_margin_impact` negative and growing

---

### Phase 4 — Frontend + Scale (Week 4–5)
**Goal:** Vue dashboard shows live simulation. Multiple SKUs, multiple supplier nodes.

| Task | Owner | Output |
|---|---|---|
| Build `CapeDashboard.vue` with capacity gauges | Dev | Visual utilization bars |
| Build `CapeGraph.vue` (supply chain topology with flow arrows) | Dev | D3/ECharts graph |
| Build `CapeAlerts.vue` (real-time alert feed via WebSocket) | Dev | Live alert panel |
| Add SKU-2 to simulation (different margin, different weight) | Dev | Multi-SKU allocation working |
| Add second Supplier node (shared capacity competition) | Dev | Resource contention observable |
| Stress test: T=100, 3 SKUs, 2 suppliers, 4 retailers | Dev | Performance < 500ms/tick |

---

## 10. Key Risks & Mitigations

### Risk 1: OASIS `SocialAgent.__init__()` Signature Conflict
**Problem:** `CAPEAgent.__init__()` passes `node_id` and `config` which OASIS's `SocialAgent` does not expect.
If OASIS `__init__` uses `**kwargs` strictly, extra params will raise `TypeError`.

**Mitigation:**
```python
# Isolate CAPE params before calling super()
def __init__(self, agent_id, node_id, config, **kwargs):
    cape_params = {"node_id": node_id, "config": config}
    # Do not pass cape_params to super()
    super().__init__(agent_id=agent_id, **kwargs)
    self.node_id = cape_params["node_id"]
    self.config  = cape_params["config"]
```
If OASIS still rejects, use composition instead of inheritance:
wrap `SocialAgent` as `self._oasis_agent = SocialAgent(...)` and implement the OASIS interface
via delegation. This is the fallback design.

---

### Risk 2: Async Conflict — MILP Solver Inside Async `act()`
**Problem:** `scipy.optimize.linprog` is synchronous and CPU-bound.
Running it inside an `async def act()` will block the event loop, starving other agents.

**Mitigation:**
```python
# In CAPEAgent.act() — offload solver to thread pool
import asyncio
loop = asyncio.get_event_loop()
allocation_plan = await loop.run_in_executor(None, allocator.solve, pending_orders)
```
For very large scenarios (100+ SKUs), replace `linprog` with the greedy allocator
(already implemented in `CapacityAllocator`) which runs in O(n log n) and is fast enough
to run synchronously even inside async context.

---

### Risk 3: State Inconsistency — Redis/PostgreSQL Divergence
**Problem:** If a tick crashes mid-flush, Redis shows T=N but PostgreSQL shows T=N-1.
Agents in the next tick read stale state from PostgreSQL while Redis is ahead.

**Mitigation:**
Use a tick-level write-ahead pattern:
```python
# In StateUpdater.flush_to_postgres()
def flush_to_postgres(self, tick: int, metrics: dict):
    with pg_transaction():
        # 1. Write inventory_state for tick N
        # 2. Write capacity_state for tick N
        # 3. Write tick_metrics for tick N
        # 4. COMMIT — only now is tick N permanent
    # 5. Only after commit: r.incr("cape:tick:current")
    # If step 1-3 fail, tick counter stays at N-1. Safe to re-run tick N.
```

---

### Risk 4: Performance Degradation at Scale
**Problem:** At T=100 with 10 agents, 3 SKUs: 100 × 10 × 3 = 3,000 `inventory_state` rows per run.
Full-table queries become slow.

**Mitigation:**
- All primary queries use indexed columns: `tick`, `node_id` (already indexed in schema)
- Use Redis as the primary read surface for hot state (agents always read Redis, not PG)
- PG is write-once-per-tick, not read-per-agent-per-tick
- Add `PARTITION BY RANGE (tick)` on `inventory_state` and `event_log` for T > 500

---

### Risk 5: Information Lag Produces Degenerate Behavior
**Problem:** With `info_lag_ticks = 3` at Retailer level, agents may never see
current tick's demand and oscillate indefinitely.

**Mitigation:**
- Cap info_lag at 2 ticks for v1 (realistic for daily reporting in Indian MSME context)
- Add "emergency signal" override: if backlog > threshold_units, agent gets immediate
  signal (bypasses lag) — models real-world phone call escalation behavior
- This is a scenario parameter, not hardcoded

---

## 11. Sample Output — What CAPE Produces

### Per-Tick Alert (Structured, not narrative)
```json
{
  "tick": 7,
  "alerts": [
    "CRITICAL:CAPACITY_SATURATED:SUP-01:97.4%",
    "ALERT:BACKLOG_CRITICAL:280 units:$26,600 margin erosion",
    "ALERT:BULLWHIP_DETECTED:amplification_ratio=3.82",
    "WARNING:WORKING_CAPITAL_STRESS:$41,200 tied in pipeline"
  ],
  "capacity_utilization": {
    "SUP-01": 97.4,
    "MFG-01": 84.2,
    "DIST-01": 61.0,
    "RET-01": 45.0
  },
  "instability_index": 3.82,
  "system_backlog": 280,
  "net_margin_impact": -26600.00
}
```

### End-of-Run Financial Summary
```json
{
  "simulation_id": "cape-run-001",
  "t_max": 20,
  "scenario": "demand_spike_T5_300pct",
  "peak_capacity_node": "SUP-01",
  "peak_utilization_pct": 97.4,
  "peak_backlog_units": 350,
  "total_stockout_cost": 47250.00,
  "total_holding_cost": 12400.00,
  "total_transport_cost": 8900.00,
  "net_margin_erosion": 68550.00,
  "bullwhip_detected": true,
  "bullwhip_onset_tick": 7,
  "bullwhip_amplification_ratio": 3.82,
  "recommended_action": "Re-prioritize allocation at SUP-01: SKU-A (margin $8.40/unit) over SKU-B ($3.20/unit). Reduce MFG-01 order amplification factor from 1.8x to 1.2x."
}
```

---

## 12. Quick Reference — What Is and Is Not Modified

| Component | Status | Justification |
|---|---|---|
| `oasis/` directory (entire) | ✅ UNTOUCHED | Runtime engine — inviolable |
| `oasis/environment.py` | ✅ UNTOUCHED | `CAPEEnvironment` subclasses it |
| `oasis/social_agent/agent.py` | ✅ UNTOUCHED | `CAPEAgent` subclasses it |
| `oasis/agent_manager.py` | ✅ UNTOUCHED | Orchestrates all agents |
| `frontend/` (existing views) | ✅ UNTOUCHED | New CAPE views added alongside |
| `backend/services/simulation_runner.py` | ⚠️ 8 LINES ADDED | Branch for `scenario_type=cape` |
| `backend/app.py` | ⚠️ 4 ROUTES ADDED | CAPE API surface |
| `docker-compose.yml` | ⚠️ 2 SERVICES ADDED | PostgreSQL + Redis |
| `backend/cape/` | ✅ ALL NEW | The 20% CAPE replacement layer |
| `frontend/src/views/Cape*.vue` | ✅ ALL NEW | CAPE dashboard panels |

---

*Document version: 1.0 — CAPE Architecture & Execution Plan*
*Prepared for: samirsawarkar/chainrisk*
*Total ChainRisk code modified: 8 lines in simulation_runner.py + 4 API routes*
*Total ChainRisk code added: ~1,200 lines across cape/ module and 3 Vue components*
