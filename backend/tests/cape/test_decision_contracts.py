from io import BytesIO

from openpyxl import Workbook

from cape.contracts import (
    build_assistant_response,
    check_input_consistency,
    compute_decision_signal,
    normalize_scenario_rows,
    parse_excel_to_json,
    validate_system_config,
)


def test_validate_system_config_requires_keys():
    errors = validate_system_config({})
    assert "Missing required field: nodes" in errors
    assert "Missing required field: skus" in errors


def test_validate_system_config_non_object():
    assert validate_system_config([]) == ["system_config must be a JSON object"]


def test_validate_system_config_bad_scalar_types():
    cfg = {
        "nodes": [{"node_id": "SUP-01", "node_type": "supplier", "capacity_units": "x"}],
        "skus": [{"sku_id": "A", "unit_margin": 1, "unit_weight": 1}],
        "lead_times": [{"from_node": "SUP-01", "to_node": "SUP-01", "lead_time_ticks": 0}],
        "initial_inventory": [{"node_id": "SUP-01", "sku_id": "A", "on_hand": "y"}],
    }
    errors = validate_system_config(cfg)
    assert any("capacity_units" in e for e in errors)
    assert any("on_hand" in e for e in errors)


def test_normalize_scenario_rows():
    rows = normalize_scenario_rows([{"time": "1", "sku": "A", "demand": "40", "shock": "0"}])
    assert rows == [{"time": 1, "sku": "A", "demand": 40, "shock": 0}]


def test_parse_excel_to_json():
    wb = Workbook()
    ws = wb.active
    ws.append(["time", "sku", "demand", "shock"])
    ws.append([1, "A", 40, 0])
    ws.append([5, "B", 70, 1])
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    rows = parse_excel_to_json(buf)
    assert rows[0]["sku"] == "A"
    assert rows[1]["shock"] == 1


def test_compute_decision_signal_critical_bullwhip():
    signal = compute_decision_signal(
        {
            "tick": 7,
            "capacity_utilization": {"SUP-01": 93.0},
            "system_backlog": 100,
            "instability_index": 2.4,
            "amplification_ratios": {"dist_over_ret": 1.7, "mfg_over_dist": 2.4, "sup_over_mfg": 1.1},
            "explainability": {
                "spike_sku": "SKU_B",
                "spike_from": 60,
                "spike_to": 180,
                "peak_capacity_node": "MFG-01",
                "peak_capacity_utilization": 92.0,
                "low_allocation_sku": "SKU_A",
            },
            "net_margin_impact": -1400000,
        }
    )
    assert signal["status"] == "critical"
    assert signal["bullwhip_detected"] is True
    assert signal["peak_node"] == "MFG-01"
    assert "SKU_B demand spike caused" in signal["root_cause"]


def test_check_input_consistency_flags_unknown_sku():
    system_config = {
        "nodes": [
            {"node_id": "SUP-01", "node_type": "supplier", "capacity_units": 100},
            {"node_id": "MFG-01", "node_type": "manufacturer", "capacity_units": 100},
        ],
        "skus": [{"sku_id": "A", "unit_margin": 10, "unit_weight": 1}],
        "lead_times": [{"from_node": "SUP-01", "to_node": "MFG-01", "lead_time_ticks": 2}],
        "initial_inventory": [{"node_id": "SUP-01", "sku_id": "A", "on_hand": 100}],
    }
    scenario_events = [{"time": 1, "sku": "B", "demand": 10, "shock": 0}]
    result = check_input_consistency(system_config, scenario_events)
    assert result["valid"] is False
    assert "Scenario contains SKUs not in system config: B" in result["errors"]


def test_assistant_responds_with_capacity_guidance():
    system_config = {
        "nodes": [
            {"node_id": "SUP-01", "node_type": "supplier", "capacity_units": 100},
            {"node_id": "MFG-01", "node_type": "manufacturer", "capacity_units": 100},
        ],
        "skus": [{"sku_id": "A", "unit_margin": 10, "unit_weight": 1}],
        "lead_times": [{"from_node": "SUP-01", "to_node": "MFG-01", "lead_time_ticks": 2}],
        "initial_inventory": [{"node_id": "SUP-01", "sku_id": "A", "on_hand": 100}],
    }
    scenario_events = [{"time": 1, "sku": "A", "demand": 10, "shock": 0}]
    result = build_assistant_response("Where is my capacity bottleneck?", system_config, scenario_events)
    assert "Capacity bottlenecks" in result["summary"]
