-- CAPE baseline schema
CREATE TABLE IF NOT EXISTS sc_nodes (
    node_id          VARCHAR(32) PRIMARY KEY,
    node_type        VARCHAR(16) NOT NULL,
    capacity_units   INTEGER NOT NULL,
    holding_cost     NUMERIC(10,4) NOT NULL,
    stockout_penalty NUMERIC(10,4) NOT NULL,
    info_lag_ticks   INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sc_arcs (
    arc_id           SERIAL PRIMARY KEY,
    from_node        VARCHAR(32) REFERENCES sc_nodes(node_id),
    to_node          VARCHAR(32) REFERENCES sc_nodes(node_id),
    lead_time_ticks  INTEGER NOT NULL,
    transport_cost   NUMERIC(10,4) NOT NULL
);

CREATE TABLE IF NOT EXISTS skus (
    sku_id           VARCHAR(32) PRIMARY KEY,
    description      TEXT,
    unit_margin      NUMERIC(10,4) NOT NULL,
    unit_weight      NUMERIC(8,4) NOT NULL
);

CREATE TABLE IF NOT EXISTS inventory_state (
    snap_id          BIGSERIAL PRIMARY KEY,
    tick             INTEGER NOT NULL,
    node_id          VARCHAR(32) REFERENCES sc_nodes(node_id),
    sku_id           VARCHAR(32) REFERENCES skus(sku_id),
    on_hand          INTEGER NOT NULL DEFAULT 0,
    backlog          INTEGER NOT NULL DEFAULT 0,
    reserved         INTEGER NOT NULL DEFAULT 0,
    UNIQUE (tick, node_id, sku_id)
);

CREATE TABLE IF NOT EXISTS pipeline_state (
    pipeline_id      BIGSERIAL PRIMARY KEY,
    order_ref        VARCHAR(64) NOT NULL,
    arc_id           INTEGER REFERENCES sc_arcs(arc_id),
    sku_id           VARCHAR(32) REFERENCES skus(sku_id),
    quantity         INTEGER NOT NULL,
    dispatched_tick  INTEGER NOT NULL,
    eta_tick         INTEGER NOT NULL,
    status           VARCHAR(16) DEFAULT 'in_transit'
);

CREATE TABLE IF NOT EXISTS capacity_state (
    snap_id          BIGSERIAL PRIMARY KEY,
    tick             INTEGER NOT NULL,
    node_id          VARCHAR(32) REFERENCES sc_nodes(node_id),
    allocated_units  INTEGER NOT NULL,
    available_units  INTEGER NOT NULL,
    utilization_pct  NUMERIC(5,2) GENERATED ALWAYS AS
                     (allocated_units::numeric / NULLIF(allocated_units + available_units, 0) * 100) STORED,
    UNIQUE (tick, node_id)
);

CREATE TABLE IF NOT EXISTS orders (
    order_id          VARCHAR(64) PRIMARY KEY,
    tick_placed       INTEGER NOT NULL,
    from_node         VARCHAR(32) REFERENCES sc_nodes(node_id),
    to_node           VARCHAR(32) REFERENCES sc_nodes(node_id),
    sku_id            VARCHAR(32) REFERENCES skus(sku_id),
    quantity_ordered  INTEGER NOT NULL,
    quantity_filled   INTEGER DEFAULT 0,
    status            VARCHAR(16) DEFAULT 'pending',
    priority          SMALLINT DEFAULT 5
);

CREATE TABLE IF NOT EXISTS event_log (
    event_id          BIGSERIAL PRIMARY KEY,
    event_type        VARCHAR(32) NOT NULL,
    tick              INTEGER NOT NULL,
    source_node       VARCHAR(32),
    target_node       VARCHAR(32),
    sku_id            VARCHAR(32),
    payload           JSONB NOT NULL,
    processed         BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS tick_metrics (
    tick                 INTEGER PRIMARY KEY,
    system_backlog       INTEGER NOT NULL,
    system_capacity_util NUMERIC(5,2) NOT NULL,
    instability_index    NUMERIC(8,4) NOT NULL,
    total_holding_cost   NUMERIC(12,4) NOT NULL,
    total_stockout_cost  NUMERIC(12,4) NOT NULL,
    total_transport_cost NUMERIC(12,4) NOT NULL,
    net_margin_impact    NUMERIC(12,4) NOT NULL,
    alert_flags          TEXT[] DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_event_log_tick ON event_log(tick, processed);
CREATE INDEX IF NOT EXISTS idx_pipeline_eta ON pipeline_state(eta_tick, status);
CREATE INDEX IF NOT EXISTS idx_inventory_node_tick ON inventory_state(node_id, tick);
