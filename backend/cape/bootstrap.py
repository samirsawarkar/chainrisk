import pathlib

from cape.db import get_pg_conn, get_redis_client


def apply_schema_migrations():
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    migrations_dir = repo_root / "backend" / "migrations"
    migration_files = sorted(migrations_dir.glob("*.sql"))
    with get_pg_conn() as conn, conn.cursor() as cur:
        for path in migration_files:
            cur.execute(path.read_text(encoding="utf-8"))
        conn.commit()


def seed_scenario(system_config: dict | None = None, sku_count: int = 1, supplier_count: int = 1):
    system_config = system_config or {}
    config_nodes = system_config.get("nodes") or []
    config_skus = system_config.get("skus") or []
    config_arcs = system_config.get("lead_times") or []
    config_inventory = system_config.get("initial_inventory") or []

    sku_count = max(1, int(sku_count))
    supplier_count = max(1, int(supplier_count))
    with get_pg_conn() as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE pipeline_state, orders, inventory_state, capacity_state, event_log, tick_metrics, sc_arcs, sc_nodes, skus RESTART IDENTITY CASCADE")

        if config_nodes:
            for node in config_nodes:
                node_id = str(node.get("node_id"))
                node_type = str(node.get("node_type"))
                capacity_units = int(node.get("capacity_units", 0))
                holding_cost = 0.1
                stockout_penalty = 2.0
                info_lag_ticks = 0 if node_type == "retailer" else 1
                cur.execute(
                    """
                    INSERT INTO sc_nodes (node_id, node_type, capacity_units, holding_cost, stockout_penalty, info_lag_ticks)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (node_id, node_type, capacity_units, holding_cost, stockout_penalty, info_lag_ticks),
                )
        else:
            for s in range(1, supplier_count + 1):
                cur.execute(
                    """
                    INSERT INTO sc_nodes (node_id, node_type, capacity_units, holding_cost, stockout_penalty, info_lag_ticks)
                    VALUES (%s, 'supplier', 400, 0.1000, 1.5000, 0)
                    """,
                    (f"SUP-{s:02d}",),
                )
            cur.execute("INSERT INTO sc_nodes VALUES ('MFG-01', 'manufacturer', 350, 0.1200, 1.8000, 1)")
            cur.execute("INSERT INTO sc_nodes VALUES ('DIST-01', 'distributor', 300, 0.0800, 2.0000, 1)")
            cur.execute("INSERT INTO sc_nodes VALUES ('RET-01', 'retailer', 250, 0.0500, 2.5000, 0)")

        if config_arcs:
            for arc in config_arcs:
                cur.execute(
                    """
                    INSERT INTO sc_arcs (from_node, to_node, lead_time_ticks, transport_cost)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        str(arc.get("from_node")),
                        str(arc.get("to_node")),
                        int(arc.get("lead_time_ticks", 1)),
                        0.2,
                    ),
                )
        else:
            for s in range(1, supplier_count + 1):
                cur.execute(
                    """
                    INSERT INTO sc_arcs (from_node, to_node, lead_time_ticks, transport_cost)
                    VALUES (%s, 'MFG-01', 2, 0.3000)
                    """,
                    (f"SUP-{s:02d}",),
                )
            cur.execute("INSERT INTO sc_arcs (from_node, to_node, lead_time_ticks, transport_cost) VALUES ('MFG-01','DIST-01',1,0.2000)")
            cur.execute("INSERT INTO sc_arcs (from_node, to_node, lead_time_ticks, transport_cost) VALUES ('DIST-01','RET-01',1,0.1500)")

        if config_skus:
            for sku in config_skus:
                sku_id = str(sku.get("sku_id"))
                cur.execute(
                    """
                    INSERT INTO skus (sku_id, description, unit_margin, unit_weight)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        sku_id,
                        f"Scenario SKU {sku_id}",
                        float(sku.get("unit_margin", 10)),
                        float(sku.get("unit_weight", 1)),
                    ),
                )
        else:
            for i in range(1, sku_count + 1):
                sku_id = f"SKU-{i:03d}"
                cur.execute(
                    """
                    INSERT INTO skus (sku_id, description, unit_margin, unit_weight)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (sku_id, f"Scenario SKU {i}", 8.0 + i, 1.0 + (i * 0.1)),
                )

        if config_inventory:
            for row in config_inventory:
                cur.execute(
                    """
                    INSERT INTO inventory_state (tick, node_id, sku_id, on_hand, backlog, reserved)
                    VALUES (0, %s, %s, %s, 0, 0)
                    """,
                    (str(row.get("node_id")), str(row.get("sku_id")), int(row.get("on_hand", 0))),
                )
        else:
            for i in range(1, sku_count + 1):
                sku_id = f"SKU-{i:03d}"
                for node, on_hand in [("MFG-01", 500), ("DIST-01", 400), ("RET-01", 300)]:
                    cur.execute(
                        """
                        INSERT INTO inventory_state (tick, node_id, sku_id, on_hand, backlog, reserved)
                        VALUES (0, %s, %s, %s, 0, 0)
                        """,
                        (node, sku_id, on_hand),
                    )
                for s in range(1, supplier_count + 1):
                    cur.execute(
                        """
                        INSERT INTO inventory_state (tick, node_id, sku_id, on_hand, backlog, reserved)
                        VALUES (0, %s, %s, 1000, 0, 0)
                        """,
                        (f"SUP-{s:02d}", sku_id),
                    )

        cur.execute("SELECT node_id, capacity_units FROM sc_nodes")
        for node_id, cap in cur.fetchall():
            cur.execute(
                "INSERT INTO capacity_state (tick,node_id,allocated_units,available_units) VALUES (0,%s,0,%s)",
                (node_id, int(cap)),
            )
        conn.commit()

    r = get_redis_client()
    r.flushdb()
    r.set("cape:tick:current", 0)
