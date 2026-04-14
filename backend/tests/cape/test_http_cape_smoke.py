"""HTTP smoke tests for CAPE routes used by the supply-chain UI (no simulation run)."""

import pytest


def _minimal_config():
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


def _scenario_both_skus():
    return [
        {"time": 1, "sku": "A", "demand": 10, "shock": 0},
        {"time": 1, "sku": "B", "demand": 10, "shock": 0},
        {"time": 5, "sku": "B", "demand": 60, "shock": 1},
    ]


@pytest.fixture
def client():
    from app import create_app

    return create_app().test_client()


def test_validate_config_ok(client):
    r = client.post("/api/cape/validate-config", json={"system_config": _minimal_config()})
    assert r.status_code == 200
    j = r.get_json()
    assert j["success"] is True
    assert j["data"]["valid"] is True


def test_validate_config_invalid_still_200_with_errors(client):
    r = client.post("/api/cape/validate-config", json={"system_config": {}})
    assert r.status_code == 200
    j = r.get_json()
    assert j["success"] is True
    assert j["data"]["valid"] is False
    assert j["data"]["errors"]


def test_graph_build_ok(client):
    r = client.post(
        "/api/cape/graph/build",
        json={"system_config": _minimal_config(), "scenario_events": _scenario_both_skus()},
    )
    assert r.status_code == 200
    j = r.get_json()
    assert j["success"] is True
    assert len(j["data"]["nodes"]) == 4


def test_graph_build_400_invalid_system(client):
    bad = {"nodes": [], "skus": [], "lead_times": [], "initial_inventory": []}
    r = client.post("/api/cape/graph/build", json={"system_config": bad, "scenario_events": []})
    assert r.status_code == 400
    j = r.get_json()
    assert j["success"] is False
    assert "error" in j


def test_consistency_check_valid(client):
    r = client.post(
        "/api/cape/input/consistency-check",
        json={"system_config": _minimal_config(), "scenario_events": _scenario_both_skus()},
    )
    assert r.status_code == 200
    j = r.get_json()
    assert j["success"] is True
    assert j["data"]["valid"] is True


def test_consistency_check_fails_when_sku_b_missing_from_scenario(client):
    scenario = [{"time": 1, "sku": "A", "demand": 10, "shock": 0}]
    r = client.post(
        "/api/cape/input/consistency-check",
        json={"system_config": _minimal_config(), "scenario_events": scenario},
    )
    assert r.status_code == 200
    j = r.get_json()
    assert j["data"]["valid"] is False
    assert any("B" in e for e in j["data"]["errors"])
