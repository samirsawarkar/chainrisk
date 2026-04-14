import os
from datetime import datetime, timezone

import redis

from cape.events.bus import schedule_event as schedule_event_on_bus

try:
    import psycopg
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "psycopg is required for CAPE LedgerAdapter. Install it with `pip install psycopg[binary]`."
    ) from exc

r = redis.Redis(
    host=os.environ.get("CAPE_REDIS_HOST", "localhost"),
    port=int(os.environ.get("CAPE_REDIS_PORT", "6379")),
    db=int(os.environ.get("CAPE_REDIS_DB", "0")),
    decode_responses=True,
)

CURRENT_TICK_KEY = "cape:tick:current"


def _get_pg_conn():
    return psycopg.connect(
        host=os.environ.get("CAPE_PG_HOST", "localhost"),
        port=int(os.environ.get("CAPE_PG_PORT", "5432")),
        dbname=os.environ.get("CAPE_PG_DB", "cape"),
        user=os.environ.get("CAPE_PG_USER", "postgres"),
        password=os.environ.get("CAPE_PG_PASSWORD", ""),
        autocommit=False,
    )


class LedgerAdapter:
    def __init__(self, node_id: str):
        self.node_id = node_id

    def get_current_tick(self) -> int:
        return int(r.get(CURRENT_TICK_KEY) or 0)

    def read_delayed_state(self, current_tick: int) -> dict:
        with _get_pg_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT info_lag_ticks FROM sc_nodes WHERE node_id = %s",
                (self.node_id,),
            )
            row = cur.fetchone()
            info_lag = int(row[0]) if row else 0
            visible_tick = max(0, current_tick - info_lag)

            cur.execute(
                """
                SELECT DISTINCT ON (sku_id) sku_id, on_hand, backlog, reserved
                FROM inventory_state
                WHERE node_id = %s AND tick <= %s
                ORDER BY sku_id, tick DESC
                """,
                (self.node_id, visible_tick),
            )
            inv_rows = cur.fetchall()

            cur.execute(
                """
                SELECT available_units
                FROM capacity_state
                WHERE node_id = %s AND tick <= %s
                ORDER BY tick DESC
                LIMIT 1
                """,
                (self.node_id, visible_tick),
            )
            cap_row = cur.fetchone()

        inventory = {
            sku_id: {"on_hand": int(on_hand), "backlog": int(backlog), "reserved": int(reserved)}
            for sku_id, on_hand, backlog, reserved in inv_rows
        }

        return {
            "node_id": self.node_id,
            "visible_tick": visible_tick,
            "current_tick": current_tick,
            "inventory": inventory,
            "capacity_avail": int(cap_row[0]) if cap_row else 0,
        }

    def write_state(self, tick: int, inventory: dict, capacity_used: int):
        pipe = r.pipeline()
        for sku_id, vals in inventory.items():
            pipe.set(f"cape:state:{self.node_id}:{sku_id}:on_hand", int(vals["on_hand"]))
            pipe.set(f"cape:state:{self.node_id}:{sku_id}:backlog", int(vals["backlog"]))
        pipe.set(f"cape:capacity:{self.node_id}:available", max(0, self._get_node_capacity() - int(capacity_used)))
        pipe.execute()

    def get_pending_orders(self, target_node: str, tick: int) -> list[dict]:
        with _get_pg_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT order_id, from_node, to_node, sku_id, quantity_ordered, quantity_filled, priority, status
                FROM orders
                WHERE to_node = %s
                  AND tick_placed <= %s
                  AND status IN ('pending', 'partial')
                ORDER BY priority ASC, tick_placed ASC
                """,
                (target_node, tick),
            )
            rows = cur.fetchall()

        return [
            {
                "order_id": order_id,
                "from_node": from_node,
                "to_node": to_node,
                "sku_id": sku_id,
                "quantity_ordered": int(quantity_ordered),
                "quantity_filled": int(quantity_filled),
                "quantity_remaining": max(0, int(quantity_ordered) - int(quantity_filled)),
                "priority": int(priority),
                "status": status,
            }
            for order_id, from_node, to_node, sku_id, quantity_ordered, quantity_filled, priority, status in rows
        ]

    def get_arc(self, from_node: str, to_node: str) -> dict:
        with _get_pg_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT arc_id, from_node, to_node, lead_time_ticks, transport_cost
                FROM sc_arcs
                WHERE from_node = %s AND to_node = %s
                LIMIT 1
                """,
                (from_node, to_node),
            )
            row = cur.fetchone()

        if row is None:
            raise ValueError(f"No arc found from {from_node} to {to_node}")

        return {
            "arc_id": int(row[0]),
            "from_node": row[1],
            "to_node": row[2],
            "lead_time_ticks": int(row[3]),
            "transport_cost": float(row[4]),
        }

    def get_sim_time(self, tick: int):
        return datetime.now(timezone.utc)

    def schedule_event(self, event, execute_at_tick: int):
        schedule_event_on_bus(event, execute_at_tick)

    def record_pipeline_dispatch(
        self,
        order_ref: str,
        from_node: str,
        to_node: str,
        sku_id: str,
        quantity: int,
        dispatched_tick: int,
        eta_tick: int,
    ):
        with _get_pg_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pipeline_state (order_ref, arc_id, sku_id, quantity, dispatched_tick, eta_tick, status)
                SELECT %s, a.arc_id, %s, %s, %s, %s, 'in_transit'
                FROM sc_arcs a
                WHERE a.from_node = %s AND a.to_node = %s
                LIMIT 1
                """,
                (order_ref, sku_id, int(quantity), int(dispatched_tick), int(eta_tick), from_node, to_node),
            )
            conn.commit()

    def mark_pipeline_delayed(self, order_ref: str, new_eta: int):
        with _get_pg_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE pipeline_state
                SET eta_tick = %s, status = 'delayed'
                WHERE order_ref = %s AND status IN ('in_transit', 'delayed')
                """,
                (int(new_eta), order_ref),
            )
            conn.commit()

    def get_pipeline_quantity(self, to_node: str, sku_id: str, after_tick: int) -> int:
        with _get_pg_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(SUM(p.quantity), 0)
                FROM pipeline_state p
                JOIN sc_arcs a ON p.arc_id = a.arc_id
                WHERE a.to_node = %s
                  AND p.sku_id = %s
                  AND p.eta_tick > %s
                  AND p.status IN ('in_transit', 'delayed')
                """,
                (to_node, sku_id, after_tick),
            )
            row = cur.fetchone()
        return int(row[0] or 0)

    def get_upstream_node(self, node_id: str) -> str:
        with _get_pg_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT from_node
                FROM sc_arcs
                WHERE to_node = %s
                ORDER BY arc_id ASC
                LIMIT 1
                """,
                (node_id,),
            )
            row = cur.fetchone()

        if row is None:
            raise ValueError(f"No upstream node found for {node_id}")
        return str(row[0])

    def get_demand_history(self, node_id: str, sku_id: str, last_n: int) -> list[int]:
        current_tick = self.get_current_tick()
        start_tick = max(0, current_tick - max(1, int(last_n)))
        with _get_pg_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT quantity_ordered
                FROM orders
                WHERE from_node = %s
                  AND sku_id = %s
                  AND tick_placed >= %s
                  AND tick_placed < %s
                ORDER BY tick_placed ASC
                """,
                (node_id, sku_id, start_tick, current_tick),
            )
            rows = cur.fetchall()
        return [int(row[0]) for row in rows]

    def get_lead_time(self, from_node: str) -> int:
        with _get_pg_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT lead_time_ticks
                FROM sc_arcs
                WHERE to_node = %s
                ORDER BY arc_id ASC
                LIMIT 1
                """,
                (from_node,),
            )
            row = cur.fetchone()

        return int(row[0]) if row else 0

    def get_sku_weight(self, sku_id: str) -> float:
        with _get_pg_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT unit_weight FROM skus WHERE sku_id = %s",
                (sku_id,),
            )
            row = cur.fetchone()
        return float(row[0]) if row else 1.0

    def get_scenario_demand_for_tick(self, tick: int) -> dict[str, int]:
        key = f"cape:scenario:demand:{int(tick)}"
        raw = r.hgetall(key) or {}
        return {str(k): int(v) for k, v in raw.items()}

    def get_scenario_shock_for_tick(self, tick: int) -> dict[str, int]:
        key = f"cape:scenario:shock:{int(tick)}"
        raw = r.hgetall(key) or {}
        return {str(k): int(v) for k, v in raw.items()}

    def _get_node_capacity(self) -> int:
        with _get_pg_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT capacity_units FROM sc_nodes WHERE node_id = %s",
                (self.node_id,),
            )
            row = cur.fetchone()
        return int(row[0]) if row else 0
