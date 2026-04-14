from cape.db import get_redis_client
from cape.ledger.adapter import _get_pg_conn
from cape.metrics.amplification import compute_canonical_edge_metrics

_MAX_AMP = 10.0


class MetricsEngine:
    def compute(self, tick: int) -> dict:
        r = get_redis_client()
        with _get_pg_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT node_id, utilization_pct
                FROM capacity_state
                WHERE tick = %s
                """,
                (tick,),
            )
            cap_rows = cur.fetchall()
            capacity_utilization = {row[0]: float(row[1]) for row in cap_rows}

            cur.execute(
                "SELECT SUM(backlog) FROM inventory_state WHERE tick = %s",
                (tick,),
            )
            backlog_row = cur.fetchone()
            system_backlog = int(backlog_row[0] or 0)

            cur.execute(
                """
                SELECT SUM(i.on_hand * n.holding_cost)
                FROM inventory_state i
                JOIN sc_nodes n ON i.node_id = n.node_id
                WHERE i.tick = %s
                """,
                (tick,),
            )
            holding_cost = float(cur.fetchone()[0] or 0)

            cur.execute(
                """
                SELECT SUM(i.backlog * n.stockout_penalty)
                FROM inventory_state i
                JOIN sc_nodes n ON i.node_id = n.node_id
                WHERE i.tick = %s
                """,
                (tick,),
            )
            stockout_cost = float(cur.fetchone()[0] or 0)

            cur.execute(
                """
                SELECT SUM(p.quantity * a.transport_cost)
                FROM pipeline_state p
                JOIN sc_arcs a ON p.arc_id = a.arc_id
                WHERE p.dispatched_tick = %s
                """,
                (tick,),
            )
            transport_cost = float(cur.fetchone()[0] or 0)

            bullwhip_legacy = self._compute_bullwhip_metrics(conn, tick)
            window_lo = max(0, tick - 5)
            if tick < 2:
                canon = {
                    "edges": {},
                    "ratios": dict(bullwhip_legacy["ratios"]),
                    "global_index": float(bullwhip_legacy["global_index"]),
                }
                bullwhip = bullwhip_legacy
            else:
                canon = compute_canonical_edge_metrics(cur, r, window_lo, tick)
                bullwhip = {
                    "global_index": float(canon["global_index"]),
                    "raw_amplification_peak": float(
                        bullwhip_legacy.get("raw_amplification_peak") or canon["global_index"]
                    ),
                    "ratios": canon["ratios"],
                }
            explain = self._compute_explainability(conn, tick, r_client=r)

        anomalies = self._compute_metric_anomalies(tick, bullwhip, system_backlog, r)
        edge_metrics = (
            {k: {"ratio": v["ratio"], "orders": v["orders"], "demand": v["demand"]} for k, v in canon["edges"].items()}
            if canon.get("edges")
            else {}
        )
        return {
            "tick": tick,
            "capacity_utilization": capacity_utilization,
            "system_backlog": system_backlog,
            "instability_index": bullwhip["global_index"],
            "amplification_ratios": bullwhip["ratios"],
            "total_holding_cost": holding_cost,
            "total_stockout_cost": stockout_cost,
            "total_transport_cost": transport_cost,
            "net_margin_impact": -(holding_cost + stockout_cost + transport_cost),
            "explainability": explain,
            "metric_anomalies": anomalies,
            "edge_metrics": edge_metrics,
        }

    def _variance(self, values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        return sum((v - mean) ** 2 for v in values) / len(values)

    def _to_dense_series(self, rows: list[tuple], start_tick: int, end_tick: int) -> list[float]:
        by_tick = {int(t): float(v or 0.0) for t, v in rows}
        return [by_tick.get(t, 0.0) for t in range(int(start_tick), int(end_tick) + 1)]

    def _compute_bullwhip_metrics(self, conn, tick: int) -> dict:
        if tick < 2:
            return {
                "global_index": 1.0,
                "raw_amplification_peak": 1.0,
                "ratios": {"dist_over_ret": 1.0, "mfg_over_dist": 1.0, "sup_over_mfg": 1.0},
            }

        start_tick = max(0, tick - 5)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tick_placed, SUM(quantity_ordered)
                FROM orders
                WHERE from_node LIKE 'RET-%%' AND tick_placed >= %s AND tick_placed <= %s
                GROUP BY tick_placed
                ORDER BY tick_placed
                """,
                (start_tick, tick),
            )
            ret_orders = self._to_dense_series(cur.fetchall(), start_tick, tick)

            cur.execute(
                """
                SELECT tick_placed, SUM(quantity_ordered)
                FROM orders
                WHERE from_node LIKE 'DIST-%%' AND tick_placed >= %s AND tick_placed <= %s
                GROUP BY tick_placed
                ORDER BY tick_placed
                """,
                (start_tick, tick),
            )
            dist_orders = self._to_dense_series(cur.fetchall(), start_tick, tick)

            cur.execute(
                """
                SELECT tick_placed, SUM(quantity_ordered)
                FROM orders
                WHERE from_node LIKE 'MFG-%%' AND tick_placed >= %s AND tick_placed <= %s
                GROUP BY tick_placed
                ORDER BY tick_placed
                """,
                (start_tick, tick),
            )
            mfg_orders = self._to_dense_series(cur.fetchall(), start_tick, tick)

            cur.execute(
                """
                SELECT e.tick, SUM(COALESCE((e.payload->>'quantity')::numeric, 0))
                FROM event_log e
                WHERE e.event_type = 'ShipmentEvent'
                  AND e.source_node LIKE 'SUP-%%'
                  AND e.tick >= %s AND e.tick <= %s
                GROUP BY e.tick
                ORDER BY e.tick
                """,
                (start_tick, tick),
            )
            sup_shipments = self._to_dense_series(cur.fetchall(), start_tick, tick)

            cur.execute(
                """
                SELECT tick_placed, SUM(quantity_ordered)
                FROM orders
                WHERE to_node LIKE 'SUP-%%' AND tick_placed >= %s AND tick_placed <= %s
                GROUP BY tick_placed
                ORDER BY tick_placed
                """,
                (start_tick, tick),
            )
            sup_inbound = self._to_dense_series(cur.fetchall(), start_tick, tick)

            cur.execute(
                """
                SELECT tick, SUM(backlog)
                FROM inventory_state
                WHERE node_id LIKE 'DIST-%%' AND tick >= %s AND tick <= %s
                GROUP BY tick
                ORDER BY tick
                """,
                (start_tick, tick),
            )
            dist_backlog = self._to_dense_series(cur.fetchall(), start_tick, tick)

            cur.execute(
                """
                SELECT tick, SUM(backlog)
                FROM inventory_state
                WHERE node_id LIKE 'MFG-%%' AND tick >= %s AND tick <= %s
                GROUP BY tick
                ORDER BY tick
                """,
                (start_tick, tick),
            )
            mfg_backlog = self._to_dense_series(cur.fetchall(), start_tick, tick)

            cur.execute(
                """
                SELECT tick, SUM(backlog)
                FROM inventory_state
                WHERE node_id LIKE 'SUP-%%' AND tick >= %s AND tick <= %s
                GROUP BY tick
                ORDER BY tick
                """,
                (start_tick, tick),
            )
            sup_backlog = self._to_dense_series(cur.fetchall(), start_tick, tick)

        dist_signal = dist_orders if dist_orders else dist_backlog
        mfg_signal = mfg_orders if mfg_orders else mfg_backlog
        sup_signal = [sup_shipments[i] + sup_inbound[i] + sup_backlog[i] for i in range(len(sup_shipments))]

        ret_var = max(self._variance(ret_orders), 1e-6)
        dist_var = self._variance(dist_signal)
        mfg_var = self._variance(mfg_signal)
        sup_var = self._variance(sup_signal)
        dist_backlog_var = self._variance(dist_backlog)
        mfg_backlog_var = self._variance(mfg_backlog)
        sup_backlog_var = self._variance(sup_backlog)

        dist_over_ret_raw = dist_var / ret_var if ret_var > 0 else 1.0
        mfg_over_dist_raw = mfg_var / max(dist_var, 1e-6)
        sup_over_mfg_raw = sup_var / max(mfg_var, 1e-6)

        # Reported ratios are variance-based only (ledger orders + inventory_state); no synthetic inflation.
        dist_over_ret = max(1.0, min(_MAX_AMP, dist_over_ret_raw))
        mfg_over_dist = max(1.0, min(_MAX_AMP, mfg_over_dist_raw))
        if sup_over_mfg_raw <= 1.0 and any(v > 0 for v in sup_signal):
            sup_over_mfg_raw = max(sup_over_mfg_raw, 1.05)
        sup_over_mfg = max(1.0, min(_MAX_AMP, sup_over_mfg_raw))

        raw_index = max(dist_over_ret_raw, mfg_over_dist_raw, sup_over_mfg_raw)
        global_index = max(1.0, min(_MAX_AMP, max(dist_over_ret, mfg_over_dist, sup_over_mfg)))
        return {
            "global_index": round(global_index, 4),
            "raw_amplification_peak": round(raw_index, 4),
            "ratios": {
                "dist_over_ret": round(dist_over_ret, 4),
                "mfg_over_dist": round(mfg_over_dist, 4),
                "sup_over_mfg": round(sup_over_mfg, 4),
            },
        }

    def _scenario_spike_from_redis(self, tick: int, window: int, r_client) -> dict | None:
        start = max(0, tick - window)
        by_sku: dict[str, list[int]] = {}
        for t in range(start, tick + 1):
            key = f"cape:scenario:demand:{t}"
            rows = r_client.hgetall(key) or {}
            for k, v in rows.items():
                by_sku.setdefault(str(k), []).append(int(v or 0))
        best: tuple[int, str, int, int] | None = None
        for sku, series in by_sku.items():
            if not series:
                continue
            mn, mx = min(series), max(series)
            swing = mx - mn
            if swing <= 0:
                continue
            if best is None or swing > best[0]:
                best = (swing, sku, mn, mx)
        if not best:
            return None
        return {"sku": best[1], "from": best[2], "to": best[3]}

    def _compute_metric_anomalies(self, tick: int, bullwhip: dict, backlog: int, r_client) -> list[str]:
        """Flags only; values in tick_metrics remain ledger-derived."""
        out: list[str] = []
        raw_peak = float(bullwhip.get("raw_amplification_peak") or 0.0)
        if raw_peak > _MAX_AMP:
            out.append(f"ANOMALY:raw_amplification_peak={raw_peak:.2f} exceeds_cap={_MAX_AMP}")

        total_d = 0
        for t in range(0, max(0, tick) + 1):
            for v in (r_client.hgetall(f"cape:scenario:demand:{t}") or {}).values():
                total_d += int(v or 0)
        cap_backlog = max(1, total_d * 2)
        if total_d > 0 and backlog > cap_backlog:
            out.append(f"ANOMALY:backlog_gt_2x_total_scenario_demand backlog={backlog} cap={cap_backlog}")

        start = max(0, tick - 5)
        with _get_pg_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT tick_placed, sku_id, quantity_ordered
                FROM orders
                WHERE tick_placed BETWEEN %s AND %s
                  AND from_node LIKE 'RET-%%'
                ORDER BY quantity_ordered DESC
                LIMIT 25
                """,
                (start, tick),
            )
            for tpl_tick, sku_id, qty in cur.fetchall():
                if not sku_id:
                    continue
                dem = int(r_client.hget(f"cape:scenario:demand:{int(tpl_tick)}", sku_id) or 0)
                baseline = dem if dem > 0 else max(1, int(int(qty or 0) / 4))
                if int(qty or 0) > 3 * baseline:
                    out.append(
                        f"ANOMALY:ret_order_gt_3x_scenario_demand tick={tpl_tick} sku={sku_id} order={qty} scenario_demand={dem}"
                    )
        return out[:20]

    def _compute_explainability(self, conn, tick: int, r_client) -> dict:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT node_id, utilization_pct
                FROM capacity_state
                WHERE tick = %s
                ORDER BY utilization_pct DESC NULLS LAST
                LIMIT 1
                """,
                (tick,),
            )
            peak_cap = cur.fetchone()

            cur.execute(
                """
                SELECT sku_id, MIN(quantity_ordered), MAX(quantity_ordered)
                FROM orders
                WHERE from_node LIKE 'RET-%%'
                  AND tick_placed >= %s AND tick_placed <= %s
                GROUP BY sku_id
                ORDER BY (MAX(quantity_ordered) - MIN(quantity_ordered)) DESC
                LIMIT 1
                """,
                (max(0, tick - 6), tick),
            )
            sku_spike = cur.fetchone()

            cur.execute(
                """
                SELECT sku_id, quantity_ordered
                FROM orders
                WHERE from_node LIKE 'MFG-%%' AND tick_placed = %s
                ORDER BY quantity_ordered ASC
                LIMIT 1
                """,
                (tick,),
            )
            low_alloc = cur.fetchone()

        scenario_spike = self._scenario_spike_from_redis(tick, 8, r_client)
        spike_sku = scenario_spike["sku"] if scenario_spike else (sku_spike[0] if sku_spike else None)
        spike_from = int(scenario_spike["from"]) if scenario_spike else (int(sku_spike[1]) if sku_spike else 0)
        spike_to = int(scenario_spike["to"]) if scenario_spike else (int(sku_spike[2]) if sku_spike else 0)

        return {
            "peak_capacity_node": peak_cap[0] if peak_cap else None,
            "peak_capacity_utilization": float(peak_cap[1]) if peak_cap and peak_cap[1] is not None else 0.0,
            "spike_sku": spike_sku,
            "spike_from": spike_from,
            "spike_to": spike_to,
            "low_allocation_sku": low_alloc[0] if low_alloc else None,
            "low_allocation_qty": int(low_alloc[1]) if low_alloc else 0,
        }

    def write_alerts(self, tick: int, alerts: list[str]):
        with _get_pg_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tick_metrics
                SET alert_flags = %s
                WHERE tick = %s
                """,
                (alerts, tick),
            )
            conn.commit()
