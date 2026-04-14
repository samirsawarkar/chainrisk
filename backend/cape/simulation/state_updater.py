import json
import os

import redis

from cape.events.schemas import CAPEEvent, CapacityEvent, DelayEvent, OrderEvent, ShipmentEvent
from cape.ledger.adapter import _get_pg_conn

r = redis.Redis(
    host=os.environ.get("CAPE_REDIS_HOST", "localhost"),
    port=int(os.environ.get("CAPE_REDIS_PORT", "6379")),
    db=int(os.environ.get("CAPE_REDIS_DB", "0")),
    decode_responses=True,
)


class StateUpdater:
    def _is_duplicate_event(self, event_id: str) -> bool:
        if not event_id:
            return False
        return bool(r.sismember("cape:events:processed", event_id))

    def _mark_event_processed(self, event_id: str):
        if not event_id:
            return
        r.sadd("cape:events:processed", event_id)
        r.expire("cape:events:processed", 24 * 60 * 60)

    def _cap_backlog(self, cur, tick: int, node_id: str, sku_id: str):
        cur.execute(
            """
            WITH demand_hist AS (
                SELECT quantity_ordered::numeric AS qty
                FROM orders
                WHERE from_node = %s
                  AND sku_id = %s
                  AND tick_placed >= %s
                  AND tick_placed <= %s
                ORDER BY tick_placed DESC
                LIMIT 5
            )
            UPDATE inventory_state i
            SET backlog = LEAST(
                i.backlog,
                LEAST(
                    200,
                    GREATEST(
                        1,
                        CAST(5 * COALESCE((SELECT AVG(qty) FROM demand_hist), 50) AS INTEGER)
                    )
                )
            )
            WHERE i.tick = %s AND i.node_id = %s AND i.sku_id = %s
            """,
            (node_id, sku_id, max(0, tick - 5), tick, tick, node_id, sku_id),
        )

    def _ensure_inventory_row(self, cur, tick: int, node_id: str, sku_id: str):
        cur.execute(
            """
            INSERT INTO inventory_state (tick, node_id, sku_id, on_hand, backlog, reserved)
            SELECT %s, %s, %s, on_hand, backlog, reserved
            FROM inventory_state
            WHERE node_id = %s AND sku_id = %s
            ORDER BY tick DESC
            LIMIT 1
            ON CONFLICT (tick, node_id, sku_id) DO NOTHING
            """,
            (tick, node_id, sku_id, node_id, sku_id),
        )

    def _log_event(self, cur, tick: int, event: CAPEEvent):
        cur.execute(
            """
            INSERT INTO event_log (event_type, tick, source_node, target_node, sku_id, payload, processed)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, TRUE)
            """,
            (
                event.event_type,
                tick,
                event.source_node,
                event.target_node,
                event.sku_id,
                json.dumps(event.model_dump(mode="json")),
            ),
        )

    def apply_events(self, tick: int, events: list):
        with _get_pg_conn() as conn, conn.cursor() as cur:
            for event in events:
                event_id = getattr(event, "event_id", "")
                if self._is_duplicate_event(event_id):
                    continue
                self._log_event(cur, tick, event)
                if isinstance(event, ShipmentEvent):
                    self._ensure_inventory_row(cur, tick, event.target_node, event.sku_id)
                    self._ensure_inventory_row(cur, tick, event.source_node, event.sku_id)
                    cur.execute(
                        """
                        UPDATE inventory_state
                        SET on_hand = on_hand + %s
                        WHERE tick = %s AND node_id = %s AND sku_id = %s
                        """,
                        (event.quantity, tick, event.target_node, event.sku_id),
                    )
                    cur.execute(
                        """
                        UPDATE inventory_state
                        SET on_hand = GREATEST(on_hand - %s, 0),
                            backlog = GREATEST(backlog - %s, 0)
                        WHERE tick = %s AND node_id = %s AND sku_id = %s
                        """,
                        (event.quantity, event.quantity, tick, event.target_node, event.sku_id),
                    )
                    cur.execute(
                        """
                        UPDATE inventory_state
                        SET on_hand = GREATEST(on_hand - %s, 0)
                        WHERE tick = %s AND node_id = %s AND sku_id = %s
                        """,
                        (event.quantity, tick, event.source_node, event.sku_id),
                    )
                    cur.execute(
                        """
                        UPDATE pipeline_state
                        SET status = 'delivered'
                        WHERE order_ref = %s AND status IN ('in_transit', 'delayed')
                        """,
                        (event.order_ref,),
                    )
                    cur.execute(
                        """
                        UPDATE orders
                        SET quantity_filled = LEAST(quantity_ordered, quantity_filled + %s),
                            status = CASE
                                WHEN quantity_filled + %s >= quantity_ordered THEN 'filled'
                                WHEN quantity_filled + %s > 0 THEN 'partial'
                                ELSE status
                            END
                        WHERE order_id = %s
                        """,
                        (event.quantity, event.quantity, event.quantity, event.order_ref),
                    )
                elif isinstance(event, DelayEvent):
                    cur.execute(
                        """
                        UPDATE pipeline_state
                        SET eta_tick = %s, status = 'delayed'
                        WHERE order_ref = %s AND status IN ('in_transit', 'delayed')
                        """,
                        (int(event.new_eta), event.order_ref),
                    )
                elif isinstance(event, OrderEvent):
                    self._ensure_inventory_row(cur, tick, event.source_node, event.sku_id)
                    cur.execute(
                        """
                        INSERT INTO orders (
                            order_id, tick_placed, from_node, to_node, sku_id, quantity_ordered, priority
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (order_id) DO NOTHING
                        RETURNING order_id
                        """,
                        (
                            event.event_id,
                            event.tick,
                            event.source_node,
                            event.target_node,
                            event.sku_id,
                            event.quantity,
                            event.priority,
                        ),
                    )
                    inserted_row = cur.fetchone()
                    if inserted_row:
                        cur.execute(
                            """
                            UPDATE inventory_state
                            SET backlog = backlog + %s
                            WHERE tick = %s AND node_id = %s AND sku_id = %s
                            """,
                            (event.quantity, tick, event.source_node, event.sku_id),
                        )
                        self._cap_backlog(cur, tick, event.source_node, event.sku_id)
                elif isinstance(event, CapacityEvent):
                    cur.execute(
                        """
                        INSERT INTO capacity_state (tick, node_id, allocated_units, available_units)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (tick, node_id) DO UPDATE
                        SET allocated_units = EXCLUDED.allocated_units,
                            available_units = EXCLUDED.available_units
                        """,
                        (
                            tick,
                            event.source_node,
                            int(event.capacity_used),
                            max(0, int(event.capacity_total) - int(event.capacity_used)),
                        ),
                    )
                self._mark_event_processed(event_id)
            conn.commit()

    def reset_capacity(self, tick: int):
        with _get_pg_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO capacity_state (tick, node_id, allocated_units, available_units)
                SELECT %s, node_id, 0, capacity_units
                FROM sc_nodes
                ON CONFLICT (tick, node_id) DO UPDATE
                SET allocated_units = 0,
                    available_units = EXCLUDED.available_units
                """,
                (tick,),
            )
            conn.commit()

    def flush_to_postgres(self, tick: int, metrics: dict):
        cap_map = metrics.get("capacity_utilization", {})
        if cap_map:
            system_capacity_util = float(sum(cap_map.values()) / len(cap_map))
        else:
            system_capacity_util = 0.0

        with _get_pg_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tick_metrics (
                    tick, system_backlog, system_capacity_util, instability_index,
                    total_holding_cost, total_stockout_cost, total_transport_cost, net_margin_impact, alert_flags,
                    edge_metrics
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (tick) DO UPDATE SET
                    system_backlog = EXCLUDED.system_backlog,
                    system_capacity_util = EXCLUDED.system_capacity_util,
                    instability_index = EXCLUDED.instability_index,
                    total_holding_cost = EXCLUDED.total_holding_cost,
                    total_stockout_cost = EXCLUDED.total_stockout_cost,
                    total_transport_cost = EXCLUDED.total_transport_cost,
                    net_margin_impact = EXCLUDED.net_margin_impact,
                    edge_metrics = EXCLUDED.edge_metrics
                """,
                (
                    tick,
                    int(metrics["system_backlog"]),
                    system_capacity_util,
                    float(metrics["instability_index"]),
                    float(metrics["total_holding_cost"]),
                    float(metrics["total_stockout_cost"]),
                    float(metrics["total_transport_cost"]),
                    float(metrics["net_margin_impact"]),
                    [],
                    json.dumps(metrics.get("edge_metrics") or {}),
                ),
            )
            conn.commit()
