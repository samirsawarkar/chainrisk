"""SKU consistency across config, scenario, and ledger tables."""

from __future__ import annotations

from typing import Iterable

# Node-level CapacityEvent uses this placeholder; it is not a product SKU in system_config.
_AGGREGATE_SKU_SENTINELS = frozenset(s.lower() for s in ("ALL", "ANY", "*"))


def allowed_skus_from_config(system_config: dict) -> set[str]:
    return {str(s.get("sku_id", "")).strip() for s in (system_config or {}).get("skus", []) if s.get("sku_id")}


def scenario_skus(scenario_events: list[dict]) -> set[str]:
    return {str(r.get("sku", "")).strip() for r in scenario_events or [] if r.get("sku")}


def validate_config_skus_covered_in_scenario(system_config: dict, scenario_events: list[dict]) -> list[str]:
    """Every configured SKU must appear in ≥1 scenario row (demand may be 0 in a dedicated row)."""
    allowed = allowed_skus_from_config(system_config)
    seen = scenario_skus(scenario_events)
    missing = sorted(allowed - seen)
    if missing:
        return [
            "Scenario must include at least one row per configured SKU (use demand 0 if idle). "
            f"Missing: {', '.join(missing)}"
        ]
    return []


def validate_sku_consistency_pg(conn, allowed_skus: Iterable[str]) -> list[str]:
    """Ensure orders, events, inventory, pipeline only reference allowed SKUs."""
    allowed = {str(s).strip() for s in allowed_skus if str(s).strip()}
    if not allowed:
        return []

    errors: list[str] = []
    tables = [
        ("orders", "sku_id"),
        ("event_log", "sku_id"),
        ("inventory_state", "sku_id"),
        ("pipeline_state", "sku_id"),
    ]
    with conn.cursor() as cur:
        for table, col in tables:
            cur.execute(
                f"""
                SELECT DISTINCT {col}
                FROM {table}
                WHERE {col} IS NOT NULL AND TRIM({col}::text) <> ''
                """,
            )
            for (val,) in cur.fetchall():
                sid = str(val).strip()
                if not sid:
                    continue
                if sid.lower() in _AGGREGATE_SKU_SENTINELS:
                    continue
                if sid not in allowed:
                    errors.append(f"Invalid SKU {sid!r} in {table}.{col} (not in system_config.skus)")
    return errors
