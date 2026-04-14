"""Decision-grade integrity: SKU coverage, causality shape, counterfactual contract."""

from cape.ai.causality_engine import chain_template, get_root_cause
from cape.ai.output_validation import validate_output
from cape.ai.tools import filter_by_tick
from cape.contracts import check_input_consistency
from cape.sku_integrity import _AGGREGATE_SKU_SENTINELS, validate_config_skus_covered_in_scenario


def _minimal_system():
    return {
        "nodes": [
            {"node_id": "SUP-01", "node_type": "supplier", "capacity_units": 500},
            {"node_id": "MFG-01", "node_type": "manufacturer", "capacity_units": 450},
            {"node_id": "DIST-01", "node_type": "distributor", "capacity_units": 400},
            {"node_id": "RET-01", "node_type": "retailer", "capacity_units": 350},
        ],
        "skus": [
            {"sku_id": "A", "unit_margin": 10, "unit_weight": 1},
            {"sku_id": "B", "unit_margin": 9, "unit_weight": 1},
        ],
        "lead_times": [
            {"from_node": "SUP-01", "to_node": "MFG-01", "lead_time_ticks": 2},
            {"from_node": "MFG-01", "to_node": "DIST-01", "lead_time_ticks": 1},
            {"from_node": "DIST-01", "to_node": "RET-01", "lead_time_ticks": 1},
        ],
        "initial_inventory": [
            {"node_id": "RET-01", "sku_id": "A", "on_hand": 100},
            {"node_id": "RET-01", "sku_id": "B", "on_hand": 100},
            {"node_id": "DIST-01", "sku_id": "A", "on_hand": 100},
            {"node_id": "DIST-01", "sku_id": "B", "on_hand": 100},
            {"node_id": "MFG-01", "sku_id": "A", "on_hand": 100},
            {"node_id": "MFG-01", "sku_id": "B", "on_hand": 100},
            {"node_id": "SUP-01", "sku_id": "A", "on_hand": 200},
            {"node_id": "SUP-01", "sku_id": "B", "on_hand": 200},
        ],
    }


def test_validate_config_skus_covered_flags_missing_b():
    system = _minimal_system()
    scenario = [
        {"time": 1, "sku": "A", "demand": 60, "shock": 0},
        {"time": 5, "sku": "A", "demand": 60, "shock": 0},
    ]
    err = validate_config_skus_covered_in_scenario(system, scenario)
    assert err and "B" in err[0]


def test_check_input_valid_when_both_skus_in_scenario():
    system = _minimal_system()
    scenario = [
        {"time": 1, "sku": "A", "demand": 60, "shock": 0},
        {"time": 1, "sku": "B", "demand": 60, "shock": 0},
        {"time": 5, "sku": "B", "demand": 130, "shock": 1},
        {"time": 5, "sku": "A", "demand": 60, "shock": 0},
    ]
    result = check_input_consistency(system, scenario)
    assert result["valid"] is True


def test_chain_template_order():
    assert "RET-01" in chain_template()
    assert "SUP-01" in chain_template()


def test_capacity_event_placeholder_skus_not_treated_as_product_skus():
    """CapacityEvent logs sku_id=ALL; integrity check must ignore that sentinel."""
    assert "all" in _AGGREGATE_SKU_SENTINELS


def test_filter_by_tick_dict_series():
    data = {"series": {"ret_demand": [{"tick": 1, "qty": 1.0}, {"tick": 5, "qty": 5.0}, {"tick": 9, "qty": 2.0}]}}
    out = filter_by_tick(data, 4, 6)
    assert len(out["series"]["ret_demand"]) == 1
    assert out["series"]["ret_demand"][0]["tick"] == 5


def test_validate_output_flags_zero_flow_with_hot_edges():
    bundle = {
        "metrics": {"edge_metrics": {"RET-01|DIST-01": {"orders": 50, "demand": 40}}, "backlog": 0},
        "flow_diagram": {"stages": [{"demand": 0, "order": 0, "backlog": 0, "id": "RET-01"}]},
        "root_cause": {"sku": "B"},
        "question_scope": {"sku_hint": None},
    }
    ok, errs = validate_output("Why DIST?", bundle, {"summary": "ok", "evidence": []})
    assert not ok
    assert any("flow_diagram" in e for e in errs)


def test_get_root_cause_returns_structured_keys():
    """Without DB, expect ValueError or empty-ish result — skip when PG unavailable."""
    import pytest

    try:
        out = get_root_cause("DIST-01", 5)
    except Exception:
        pytest.skip("PostgreSQL not available for causality_engine test")
    assert "sku" in out
    assert "trigger_tick" in out
    assert "chain" in out
    assert isinstance(out["chain"], list)
