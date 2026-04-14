from cape.db import get_pg_conn, get_redis_client


def main() -> None:
    with get_pg_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sc_nodes (node_id, node_type, capacity_units, holding_cost, stockout_penalty, info_lag_ticks)
            VALUES
              ('SUP-01', 'supplier', 400, 0.1000, 1.5000, 0),
              ('MFG-01', 'manufacturer', 350, 0.1200, 1.8000, 1),
              ('DIST-01', 'distributor', 300, 0.0800, 2.0000, 1),
              ('RET-01', 'retailer', 250, 0.0500, 2.5000, 0)
            ON CONFLICT (node_id) DO NOTHING
            """
        )

        cur.execute(
            """
            INSERT INTO sc_arcs (from_node, to_node, lead_time_ticks, transport_cost)
            VALUES
              ('SUP-01', 'MFG-01', 2, 0.3000),
              ('MFG-01', 'DIST-01', 1, 0.2000),
              ('DIST-01', 'RET-01', 1, 0.1500)
            ON CONFLICT DO NOTHING
            """
        )

        cur.execute(
            """
            INSERT INTO skus (sku_id, description, unit_margin, unit_weight)
            VALUES ('SKU-001', 'Baseline SKU', 9.5000, 1.0000)
            ON CONFLICT (sku_id) DO NOTHING
            """
        )

        cur.execute(
            """
            INSERT INTO inventory_state (tick, node_id, sku_id, on_hand, backlog, reserved)
            VALUES
              (0, 'SUP-01', 'SKU-001', 1000, 0, 0),
              (0, 'MFG-01', 'SKU-001', 500, 0, 0),
              (0, 'DIST-01', 'SKU-001', 400, 0, 0),
              (0, 'RET-01', 'SKU-001', 300, 0, 0)
            ON CONFLICT (tick, node_id, sku_id) DO NOTHING
            """
        )

        cur.execute(
            """
            INSERT INTO capacity_state (tick, node_id, allocated_units, available_units)
            VALUES
              (0, 'SUP-01', 0, 400),
              (0, 'MFG-01', 0, 350),
              (0, 'DIST-01', 0, 300),
              (0, 'RET-01', 0, 250)
            ON CONFLICT (tick, node_id) DO NOTHING
            """
        )

        conn.commit()

    r = get_redis_client()
    r.set("cape:tick:current", 0)

    print("Seeded CAPE baseline scenario")


if __name__ == "__main__":
    main()
