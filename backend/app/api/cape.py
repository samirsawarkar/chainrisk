import os
import traceback
import io
import csv
import json
import re
import threading
import time
from typing import Optional

import redis
from flask import jsonify, request, Response
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas

from . import cape_bp
from cape.bootstrap import apply_schema_migrations, seed_scenario
from cape.ai.agent import CAPEChatAgent
from cape.contracts import (
    build_assistant_response,
    check_input_consistency,
    compute_decision_signal,
    normalize_scenario_rows,
    parse_excel_to_json,
    parse_json_scenario,
    validate_system_config,
)
from cape.ledger.adapter import _get_pg_conn
from cape.simulation.metrics import MetricsEngine
from cape.ai.counterfactual import simulate_adjustment as cape_simulate_adjustment
from cape.db import get_redis_client
from cape.visuals import (
    build_amplification_figure,
    build_backlog_figure,
    build_bullwhip_figure,
    build_capacity_figure,
    build_timeline_data,
    get_amplification_data,
    get_backlog_data,
    get_bullwhip_data,
    get_capacity_data,
)
from cape.visuals.pro_workspace import (
    build_whatif_preview,
    bullwhip_pro_plotly_figure_json,
    get_bullwhip_pro,
    get_capacity_heatmap,
    get_causality_payload,
    get_flow_network,
    get_node_tick_detail,
    parse_tick_range,
)
from ..services.simulation_runner import SimulationRunner
from ..utils.logger import get_logger

logger = get_logger("chainrisk.api.cape")

r = redis.Redis(
    host=os.environ.get("CAPE_REDIS_HOST", "localhost"),
    port=int(os.environ.get("CAPE_REDIS_PORT", "6379")),
    db=int(os.environ.get("CAPE_REDIS_DB", "0")),
    decode_responses=True,
)

_run_lock = threading.Lock()
_run_tasks: dict[str, dict] = {}
_latest_run_task_id: Optional[str] = None
_chat_agent = CAPEChatAgent()


def _normalize_chat_response(result: dict) -> dict:
    if not isinstance(result, dict):
        return {
            "summary": "No answer generated.",
            "direct_answer": "No answer generated.",
            "evidence": [],
            "causal_chain": [],
            "impact": [],
            "decision": "Re-run simulation and ask with node/tick details.",
            "charts": [],
            "diagram": {"nodes": [], "edges": []},
        }
    if "charts" in result and "diagram" in result and "evidence" in result:
        result.setdefault("causal_chain", [])
        result.setdefault("decision", "")
        result.setdefault("direct_answer", result.get("summary", ""))
        result.setdefault("impact", [])
        return result
    # Backward-compatible mapping from old contract
    details = result.get("details") or {}
    event_lines = details.get("event_lines") or []
    evidence = []
    if result.get("recommendation"):
        evidence.append(str(result.get("recommendation")))
    evidence.extend([str(line) for line in event_lines[:5]])
    return {
        "summary": str(result.get("summary", "")),
        "direct_answer": str(result.get("summary", "")),
        "evidence": evidence,
        "causal_chain": details.get("events") or [],
        "impact": [],
        "decision": str(result.get("recommendation", "")),
        "charts": [],
        "diagram": {"nodes": [], "edges": []},
    }


def _to_jsonb(value):
    return json.dumps(value or {})


def _persist_project(
    project_id: str,
    project_name: str,
    system_config: dict,
    scenario_events: list,
    scenario_file_name: str = "",
):
    with _get_pg_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO cape_projects (
                project_id, project_name, scenario_file_name, system_config, scenario_events, latest_status
            )
            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, 'draft')
            ON CONFLICT (project_id) DO UPDATE
            SET
                project_name = EXCLUDED.project_name,
                scenario_file_name = EXCLUDED.scenario_file_name,
                system_config = EXCLUDED.system_config,
                scenario_events = EXCLUDED.scenario_events,
                updated_at = NOW()
            """,
            (project_id, project_name, scenario_file_name, _to_jsonb(system_config), _to_jsonb(scenario_events)),
        )
        conn.commit()


def _update_project_run_snapshot(project_id: str, status: str):
    tick = int(r.get("cape:tick:current") or 0)
    latest_tick = max(0, tick - 1)
    metrics = MetricsEngine().compute(latest_tick) if latest_tick >= 0 else {}
    decision = compute_decision_signal(metrics) if metrics else {}
    visual_summary = {
        "instability_index": float(metrics.get("instability_index", 0.0) or 0.0),
        "system_backlog": int(metrics.get("system_backlog", 0) or 0),
        "peak_capacity_util": float(metrics.get("system_capacity_util", 0.0) or 0.0),
        "bullwhip_detected": bool(decision.get("bullwhip_detected", False)),
        "root_cause": str(decision.get("root_cause", "")),
    }
    with _get_pg_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE cape_projects
            SET
                latest_status = %s,
                latest_decision = %s::jsonb,
                latest_metrics = %s::jsonb,
                latest_visual_summary = %s::jsonb,
                updated_at = NOW(),
                last_run_at = NOW()
            WHERE project_id = %s
            """,
            (status, _to_jsonb(decision), _to_jsonb(metrics), _to_jsonb(visual_summary), project_id),
        )
        conn.commit()


def _append_project_chat(project_id: str, question: str, answer: dict):
    with _get_pg_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT chat_history FROM cape_projects WHERE project_id = %s LIMIT 1", (project_id,))
        row = cur.fetchone()
        if not row:
            return
        history = row[0] if isinstance(row[0], list) else []
        history.append(
            {
                "time": int(time.time()),
                "question": question,
                "answer": answer,
            }
        )
        history = history[-100:]
        cur.execute(
            """
            UPDATE cape_projects
            SET chat_history = %s::jsonb, updated_at = NOW()
            WHERE project_id = %s
            """,
            (json.dumps(history), project_id),
        )
        conn.commit()


def _save_project_report(project_id: str, report: dict):
    with _get_pg_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE cape_projects
            SET latest_report = %s::jsonb, updated_at = NOW()
            WHERE project_id = %s
            """,
            (json.dumps(report or {}), project_id),
        )
        conn.commit()


def _resolve_tick_window(start_tick: Optional[int], end_tick: Optional[int]) -> tuple[int, int]:
    current_tick = int(r.get("cape:tick:current") or 0)
    latest_tick = max(0, current_tick - 1)
    end_v = latest_tick if end_tick is None else max(0, int(end_tick))
    start_v = max(0, end_v - 9) if start_tick is None else max(0, int(start_tick))
    if start_v > end_v:
        start_v, end_v = end_v, start_v
    return start_v, end_v


def _figure_png_response(fig):
    output = io.BytesIO()
    canvas = FigureCanvas(fig)
    canvas.print_png(output)
    output.seek(0)
    return Response(output.getvalue(), mimetype="image/png")


def _seed_scenario_events_to_redis(scenario_rows: list[dict]):
    tick_keys = set()
    for row in scenario_rows:
        tick = int(row.get("time", 0))
        sku = str(row.get("sku", "")).strip()
        if tick <= 0 or not sku:
            continue
        demand_key = f"cape:scenario:demand:{tick}"
        shock_key = f"cape:scenario:shock:{tick}"
        r.hset(demand_key, sku, int(row.get("demand", 0)))
        r.hset(shock_key, sku, int(row.get("shock", 0)))
        tick_keys.add(demand_key)
        tick_keys.add(shock_key)
    for key in tick_keys:
        r.expire(key, 86400)


def _build_supply_chain_graph(system_config: dict, scenario_events: list[dict]) -> dict:
    nodes = []
    edges = []
    for node in system_config.get("nodes", []):
        nodes.append(
            {
                "id": node.get("node_id"),
                "label": node.get("node_id"),
                "type": node.get("node_type"),
                "capacity_units": int(node.get("capacity_units", 0)),
            }
        )
    for idx, arc in enumerate(system_config.get("lead_times", []), start=1):
        edges.append(
            {
                "id": f"arc-{idx}",
                "source": arc.get("from_node"),
                "target": arc.get("to_node"),
                "lead_time_ticks": int(arc.get("lead_time_ticks", 0)),
            }
        )
    scenario_by_sku: dict[str, int] = {}
    for row in scenario_events:
        sku = str(row.get("sku", "")).strip()
        if not sku:
            continue
        scenario_by_sku[sku] = scenario_by_sku.get(sku, 0) + int(row.get("demand", 0))
    return {
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "sku_count": len(system_config.get("skus", [])),
            "scenario_demand_by_sku": scenario_by_sku,
        },
    }


def _build_setup_payload(system_config: dict) -> dict:
    agents = []
    schedule = []
    for idx, node in enumerate(system_config.get("nodes", []), start=1):
        node_id = node.get("node_id")
        node_type = node.get("node_type")
        agents.append(
            {
                "agent_id": f"agent-{idx:02d}",
                "node_id": node_id,
                "role": node_type,
                "persona": f"{node_type}_operator",
            }
        )
        schedule.append({"node_id": node_id, "decision_window": "every_tick", "priority": idx})
    return {"agents": agents, "schedule": schedule, "platform": "cape-single-environment"}


def _extract_tick_range_and_node(question: str):
    q = (question or "").upper()
    node_match = re.search(r"\b(SUP|MFG|DIST|RET)-\d{2}\b", q)
    node_id = node_match.group(0) if node_match else None

    # Examples: T=5-6, t 5 to 6, tick 5-6
    range_match = re.search(r"(?:T|TICK)\s*=?\s*(\d+)\s*(?:-|TO)\s*(\d+)", q)
    single_match = re.search(r"(?:T|TICK)\s*=?\s*(\d+)", q)
    if range_match:
        start_tick = int(range_match.group(1))
        end_tick = int(range_match.group(2))
    elif single_match:
        start_tick = int(single_match.group(1))
        end_tick = start_tick
    else:
        start_tick = None
        end_tick = None

    if start_tick is not None and end_tick is not None and start_tick > end_tick:
        start_tick, end_tick = end_tick, start_tick

    return start_tick, end_tick, node_id


def _trace_answer_for_question(question: str):
    start_tick, end_tick, node_id = _extract_tick_range_and_node(question)
    q = (question or "").lower()
    if start_tick is None and end_tick is None and not node_id:
        return None
    if "decision" not in q and "take" not in q and "did" not in q and "what" not in q:
        return None

    rows = r.xrevrange("cape:events:queue", count=3000)
    events = []
    for _, data in rows:
        payload_raw = data.get("payload")
        if not payload_raw:
            continue
        payload = json.loads(payload_raw)
        tick = int(payload.get("tick", -1))
        if start_tick is not None and end_tick is not None and not (start_tick <= tick <= end_tick):
            continue
        source_node = str(payload.get("source_node") or "")
        target_node = str(payload.get("target_node") or "")
        if node_id and node_id not in (source_node, target_node):
            continue
        event_type = payload.get("event_type")
        if event_type not in {"OrderEvent", "DelayEvent", "CapacityEvent", "ShipmentEvent"}:
            continue
        events.append(
            {
                "tick": tick,
                "event_type": event_type,
                "source_node": source_node,
                "target_node": target_node,
                "sku_id": payload.get("sku_id"),
                "quantity": payload.get("quantity"),
                "reason": payload.get("reorder_reason") or payload.get("delay_reason") or "",
            }
        )

    events.sort(key=lambda e: (e["tick"], e["event_type"]))
    if not events:
        target = node_id or "requested node"
        tick_text = f"T={start_tick}-{end_tick}" if start_tick is not None and end_tick is not None else "the requested ticks"
        return {
            "summary": f"No decision events found for {target} in {tick_text}.",
            "recommendation": "Try a broader tick range or ask without a node filter.",
            "details": {"events": [], "node_id": node_id, "tick_range": [start_tick, end_tick]},
        }

    target = node_id or "the system"
    tick_text = f"T={start_tick}-{end_tick}" if start_tick is not None and end_tick is not None else "requested ticks"
    top_events = events[:12]
    event_lines = [
        f"T{e['tick']} {e['event_type']} {e['source_node']}->{e['target_node']} sku={e['sku_id']} qty={e['quantity']} {e['reason']}".strip()
        for e in top_events
    ]
    return {
        "summary": f"Found {len(events)} decision events for {target} in {tick_text}.",
        "recommendation": "Review the event list to trace causality; compare with failure trace for the same ticks.",
        "details": {
            "node_id": node_id,
            "tick_range": [start_tick, end_tick],
            "events": top_events,
            "event_lines": event_lines,
        },
    }


@cape_bp.route("/validate-config", methods=["POST"])
def validate_config():
    try:
        payload = request.get_json(silent=True)
        if payload is None and request.data:
            return jsonify({"success": False, "error": "Request body must be valid JSON"}), 400
        if not isinstance(payload, dict):
            payload = {}
        system_config = payload.get("system_config")
        if system_config is None:
            system_config = {}
        if not isinstance(system_config, dict):
            return jsonify(
                {
                    "success": True,
                    "data": {"valid": False, "errors": ["system_config must be a JSON object"]},
                }
            )
        errors = validate_system_config(system_config)
        # success=True: request handled; use data.valid / data.errors for semantics (axios treats success=false as error).
        return jsonify({"success": True, "data": {"valid": len(errors) == 0, "errors": errors}})
    except Exception as e:
        logger.exception("validate-config failed")
        # Always 200 so the axios success path delivers errors to the UI (no generic HTTP 500 + empty body).
        return jsonify(
            {
                "success": True,
                "data": {
                    "valid": False,
                    "errors": [f"Internal error while validating config: {e!s}"],
                },
            }
        )


@cape_bp.route("/scenario/upload", methods=["POST"])
def upload_scenario():
    try:
        if "file" not in request.files:
            return jsonify({"success": False, "error": "file is required"}), 400
        file_obj = request.files["file"]
        filename = file_obj.filename.lower()
        if filename.endswith(".xlsx") or filename.endswith(".xlsm"):
            scenario = parse_excel_to_json(file_obj)
        elif filename.endswith(".csv"):
            content = file_obj.read().decode("utf-8")
            stripped = content.lstrip()
            if stripped.startswith("{") or stripped.startswith("["):
                payload = json.loads(content)
                if isinstance(payload, list):
                    scenario = normalize_scenario_rows(payload)
                else:
                    scenario = parse_json_scenario(payload)
            else:
                reader = csv.DictReader(io.StringIO(content))
                scenario = normalize_scenario_rows(list(reader))
                if len(scenario) == 0:
                    return jsonify({"success": False, "error": "No rows parsed. Expected columns: time, sku (or sku_id), demand (or quantity), shock"}), 400
        else:
            return jsonify({"success": False, "error": "Only Excel/CSV supported for scenario upload"}), 400
        return jsonify({"success": True, "data": {"scenario_events": scenario}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@cape_bp.route("/run", methods=["POST"])
def run_cape():
    try:
        payload = request.get_json() or {}
        system_config = payload.get("system_config", {})
        scenario_events = payload.get("scenario_events", [])
        config = payload.get("config", {})
        errors = validate_system_config(system_config)
        if errors:
            return jsonify({"success": False, "error": "Invalid system_config", "errors": errors}), 400
        if not isinstance(scenario_events, list):
            return jsonify({"success": False, "error": "scenario_events must be an array"}), 400
        consistency = check_input_consistency(system_config, scenario_events)
        if not consistency["valid"]:
            return jsonify({"success": False, "error": "Input consistency check failed", "details": consistency}), 400
        config.setdefault("t_max", 10)
        config.setdefault("backlog_alert_threshold", 100)
        config.setdefault("avg_stockout_penalty", 5)
        config["scenario_type"] = "cape"
        config["scenario_events"] = normalize_scenario_rows(scenario_events)
        config["system_config"] = system_config
        apply_schema_migrations()
        seed_scenario(
            system_config=system_config,
            sku_count=int(config.get("sku_count", 1)),
            supplier_count=int(config.get("supplier_count", 1)),
        )
        _seed_scenario_events_to_redis(config["scenario_events"])
        simulation_id = payload.get("simulation_id", f"cape-{int(time.time())}")
        project_id = payload.get("project_id")
        task_id = f"cape-run-{int(time.time() * 1000)}"
        debug_info = {
            "node_count": len(system_config.get("nodes", [])),
            "sku_count": len(system_config.get("skus", [])),
            "arc_count": len(system_config.get("lead_times", [])),
            "inventory_rows": len(system_config.get("initial_inventory", [])),
            "scenario_rows": len(config["scenario_events"]),
            "skus": [str(s.get("sku_id")) for s in system_config.get("skus", []) if s.get("sku_id")],
        }
        logger.info(f"CAPE run config injection: {debug_info}")
        task_state = {
            "task_id": task_id,
            "simulation_id": simulation_id,
            "status": "running",
            "error": None,
            "started_at": time.time(),
            "finished_at": None,
            "result": None,
            "debug": debug_info,
            "project_id": project_id,
        }
        with _run_lock:
            global _latest_run_task_id
            _run_tasks[task_id] = task_state
            _latest_run_task_id = task_id

        def _run_background():
            try:
                state = SimulationRunner._start_cape_simulation(simulation_id=simulation_id, config=config)
                with _run_lock:
                    _run_tasks[task_id]["status"] = "completed"
                    _run_tasks[task_id]["result"] = state.to_dict()
                    _run_tasks[task_id]["finished_at"] = time.time()
                if project_id:
                    _update_project_run_snapshot(project_id, "completed")
            except Exception as run_exc:
                logger.error(f"CAPE async run failed: {run_exc}")
                with _run_lock:
                    _run_tasks[task_id]["status"] = "failed"
                    _run_tasks[task_id]["error"] = str(run_exc)
                    _run_tasks[task_id]["finished_at"] = time.time()
                if project_id:
                    _update_project_run_snapshot(project_id, "failed")

        threading.Thread(target=_run_background, daemon=True).start()
        return jsonify(
            {
                "success": True,
                "data": {
                    "task_id": task_id,
                    "simulation_id": simulation_id,
                    "status": "running",
                    "project_id": project_id,
                    "debug": debug_info,
                    "run_audit": {
                        "nodes": debug_info["node_count"],
                        "skus": debug_info["sku_count"],
                        "lead_time_arcs": debug_info["arc_count"],
                        "initial_inventory_rows": debug_info["inventory_rows"],
                        "scenario_rows": debug_info["scenario_rows"],
                    },
                },
            }
        )
    except Exception as e:
        logger.error(f"CAPE run failed: {e}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@cape_bp.route("/run-status", methods=["GET"])
def get_cape_run_status():
    task_id = request.args.get("task_id")
    with _run_lock:
        selected_task_id = task_id or _latest_run_task_id
        task = _run_tasks.get(selected_task_id) if selected_task_id else None
    if not task:
        return jsonify({"success": True, "data": {"status": "idle", "current_tick": int(r.get("cape:tick:current") or 0), "total_ticks": 0, "recent_events": []}})

    current_tick = int(r.get("cape:tick:current") or 0)
    result_data = task.get("result") if isinstance(task.get("result"), dict) else {}
    expected_total_ticks = int(result_data.get("total_round") or result_data.get("max_round") or 0)
    if expected_total_ticks <= 0:
        expected_total_ticks = int(result_data.get("current_round") or 0) if task.get("status") == "completed" else max(1, current_tick)
    total_ticks = int(result_data.get("current_round") or 0) if task.get("status") == "completed" else current_tick
    progress_percent = round(min(100.0, (float(current_tick) / max(1.0, float(expected_total_ticks))) * 100.0), 2)
    stream_rows = r.xrevrange("cape:events:queue", count=20)
    recent_events = []
    for _, data in reversed(stream_rows):
        payload_raw = data.get("payload")
        if not payload_raw:
            continue
        payload = json.loads(payload_raw)
        recent_events.append(
            {
                "tick": int(payload.get("tick", current_tick)),
                "message": f"{payload.get('event_type', 'Event')} {payload.get('source_node', '')}->{payload.get('target_node', '')} sku={payload.get('sku_id', '')}",
            }
        )

    return jsonify(
        {
            "success": True,
            "data": {
                "task_id": task.get("task_id"),
                "simulation_id": task.get("simulation_id"),
                "status": task.get("status"),
                "error": task.get("error"),
                "current_tick": current_tick,
                "total_ticks": total_ticks,
                "expected_total_ticks": expected_total_ticks,
                "progress_percent": progress_percent,
                "recent_events": recent_events[-20:],
                "debug": task.get("debug") or {},
            },
        }
    )


@cape_bp.route("/graph/build", methods=["POST"])
def build_supply_chain_graph():
    payload = request.get_json() or {}
    system_config = payload.get("system_config", {})
    scenario_events = normalize_scenario_rows(payload.get("scenario_events", []))
    errors = validate_system_config(system_config)
    if errors:
        return jsonify({"success": False, "error": "Invalid system_config", "errors": errors}), 400
    graph = _build_supply_chain_graph(system_config, scenario_events)
    return jsonify({"success": True, "data": graph})


@cape_bp.route("/setup/create", methods=["POST"])
def create_supply_chain_setup():
    payload = request.get_json() or {}
    system_config = payload.get("system_config", {})
    errors = validate_system_config(system_config)
    if errors:
        return jsonify({"success": False, "error": "Invalid system_config", "errors": errors}), 400
    setup = _build_setup_payload(system_config)
    return jsonify({"success": True, "data": setup})


@cape_bp.route("/input/consistency-check", methods=["POST"])
def input_consistency_check():
    payload = request.get_json() or {}
    system_config = payload.get("system_config", {})
    scenario_events = payload.get("scenario_events", [])
    result = check_input_consistency(system_config, scenario_events)
    return jsonify({"success": True, "data": result})


@cape_bp.route("/assistant/ask", methods=["POST"])
def assistant_ask():
    payload = request.get_json() or {}
    question = payload.get("question", "")
    system_config = payload.get("system_config", {})
    scenario_events = payload.get("scenario_events", [])
    decision_signal = payload.get("decision_signal")
    result = build_assistant_response(question, system_config, scenario_events, decision_signal)
    return jsonify({"success": True, "data": result})


@cape_bp.route("/decision/latest", methods=["GET"])
def get_latest_decision_signal():
    try:
        tick = int(r.get("cape:tick:current") or 0)
        latest_tick = max(0, tick - 1)
        metrics = MetricsEngine().compute(latest_tick)
        signal = compute_decision_signal(metrics)
        return jsonify({"success": True, "data": signal})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@cape_bp.route("/metrics/<int:tick>", methods=["GET"])
def get_cape_metrics(tick: int):
    try:
        metrics = MetricsEngine().compute(tick)
        return jsonify({"success": True, "data": metrics})
    except Exception as e:
        logger.error(f"CAPE metrics failed: {e}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@cape_bp.route("/metrics/export.csv", methods=["GET"])
def export_metrics_csv():
    try:
        current_tick = int(r.get("cape:tick:current") or 0)
        rows = []
        for tick in range(0, current_tick + 1):
            metrics = MetricsEngine().compute(tick)
            rows.append(metrics)
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "tick",
                "system_backlog",
                "instability_index",
                "total_holding_cost",
                "total_stockout_cost",
                "total_transport_cost",
                "net_margin_impact",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in writer.fieldnames})
        return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=cape_metrics.csv"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@cape_bp.route("/alerts", methods=["GET"])
def get_cape_alerts():
    try:
        limit = request.args.get("limit", 50, type=int)
        with _get_pg_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT tick, alert_flags
                FROM tick_metrics
                WHERE array_length(alert_flags, 1) > 0
                ORDER BY tick DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
        alerts = [{"tick": int(row[0]), "alerts": row[1] or []} for row in rows]
        return jsonify({"success": True, "data": alerts})
    except Exception as e:
        logger.error(f"CAPE alerts failed: {e}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@cape_bp.route("/state/live", methods=["GET"])
def get_cape_live_state():
    try:
        tick = int(r.get("cape:tick:current") or 0)
        latest_tick = max(0, tick - 1)
        node_id = request.args.get("node_id")
        sku_id = request.args.get("sku_id")
        with _get_pg_conn() as conn, conn.cursor() as cur:
            if node_id and sku_id:
                cur.execute(
                    """
                    SELECT i.node_id, i.sku_id, i.on_hand, i.backlog, c.available_units
                    FROM inventory_state i
                    LEFT JOIN capacity_state c ON c.tick = i.tick AND c.node_id = i.node_id
                    WHERE i.tick = %s AND i.node_id = %s AND i.sku_id = %s
                    """,
                    (latest_tick, node_id, sku_id),
                )
            else:
                cur.execute(
                    """
                    SELECT i.node_id, i.sku_id, i.on_hand, i.backlog, c.available_units
                    FROM inventory_state i
                    LEFT JOIN capacity_state c ON c.tick = i.tick AND c.node_id = i.node_id
                    WHERE i.tick = %s
                    ORDER BY i.node_id, i.sku_id
                    """,
                    (latest_tick,),
                )
            rows = cur.fetchall()

        state_values = [
            {
                "node_id": row[0],
                "sku_id": row[1],
                "on_hand": int(row[2]),
                "backlog": int(row[3]),
                "capacity_available": int(row[4] or 0),
            }
            for row in rows
        ]
        return jsonify({"success": True, "data": {"tick": latest_tick, "state": state_values}})
    except Exception as e:
        logger.error(f"CAPE live state failed: {e}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


def _failure_trace_data_for_tick(tick: int) -> Optional[dict]:
    """
    Build failure-trace payload for embedding in reports.
    Returns None if there is no tick_metrics row for this tick (no sim data yet).
    """
    with _get_pg_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT system_backlog, system_capacity_util, instability_index, alert_flags
            FROM tick_metrics
            WHERE tick = %s
            """,
            (tick,),
        )
        metric_row = cur.fetchone()

    if metric_row is None:
        return None

    backlog, cap_util, instability, alerts = metric_row
    stream_rows = r.xrevrange("cape:events:queue", count=250)
    decisions = []
    for _, data in stream_rows:
        payload_raw = data.get("payload")
        if not payload_raw:
            continue
        payload = json.loads(payload_raw)
        if int(payload.get("tick", -1)) != tick:
            continue
        event_type = payload.get("event_type")
        if event_type not in {"OrderEvent", "DelayEvent", "CapacityEvent", "ShipmentEvent"}:
            continue
        decisions.append(
            {
                "event_type": event_type,
                "source_node": payload.get("source_node"),
                "target_node": payload.get("target_node"),
                "sku_id": payload.get("sku_id"),
                "reason": payload.get("reorder_reason") or payload.get("delay_reason"),
                "quantity": payload.get("quantity"),
            }
        )

    likely_cause = "normal_variation"
    if float(instability) > 2.0:
        likely_cause = "bullwhip_amplification"
    elif float(cap_util) > 90.0:
        likely_cause = "capacity_contention"
    elif int(backlog) > 0:
        likely_cause = "unfilled_demand"

    return {
        "tick": tick,
        "likely_cause": likely_cause,
        "metrics": {
            "system_backlog": int(backlog),
            "system_capacity_util": float(cap_util),
            "instability_index": float(instability),
            "alerts": alerts or [],
        },
        "decision_events": decisions,
    }


@cape_bp.route("/trace/failures/<int:tick>", methods=["GET"])
def get_failure_trace(tick: int):
    try:
        data = _failure_trace_data_for_tick(tick)
        if data is None:
            return jsonify({"success": False, "error": f"No metrics found for tick {tick}"}), 404
        return jsonify({"success": True, "data": data})
    except Exception as e:
        logger.error(f"CAPE failure trace failed: {e}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@cape_bp.route("/report/latest", methods=["GET"])
def get_latest_report():
    try:
        tick = int(r.get("cape:tick:current") or 0)
        latest_tick = max(0, tick - 1)
        metrics = MetricsEngine().compute(latest_tick)
        decision = compute_decision_signal(metrics)
        try:
            trace_data = _failure_trace_data_for_tick(latest_tick) or {}
        except Exception as trace_err:
            logger.warning(f"CAPE report/latest: failure trace skipped: {trace_err}")
            trace_data = {}
        report = {
            "tick": latest_tick,
            "executive_summary": f"System is {decision.get('status', 'unknown')} at tick {latest_tick}.",
            "decision": decision,
            "metrics": metrics,
            "failure_trace": trace_data,
            "actions": [
                f"Focus mitigation at {decision.get('causing_node', 'critical node')}",
                f"Address amplification zone: {decision.get('amplification_location', 'none')}",
                decision.get("recommendation", "Review node-level utilization > 90%"),
            ],
        }
        return jsonify({"success": True, "data": report})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@cape_bp.route("/visuals/bullwhip", methods=["GET"])
def get_bullwhip_visual():
    try:
        out_format = (request.args.get("format") or "json").lower()
        start_tick, end_tick = _resolve_tick_window(request.args.get("start_tick", type=int), request.args.get("end_tick", type=int))
        with _get_pg_conn() as conn:
            data = get_bullwhip_data(conn, start_tick, end_tick)
        if out_format == "png":
            fig = build_bullwhip_figure(data)
            return _figure_png_response(fig)
        return jsonify({"success": True, "data": {"start_tick": start_tick, "end_tick": end_tick, **data}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@cape_bp.route("/visuals/capacity", methods=["GET"])
def get_capacity_visual():
    try:
        out_format = (request.args.get("format") or "json").lower()
        start_tick, end_tick = _resolve_tick_window(request.args.get("start_tick", type=int), request.args.get("end_tick", type=int))
        with _get_pg_conn() as conn:
            data = get_capacity_data(conn, start_tick, end_tick)
        if out_format == "png":
            fig = build_capacity_figure(data)
            return _figure_png_response(fig)
        return jsonify({"success": True, "data": {"start_tick": start_tick, "end_tick": end_tick, **data}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@cape_bp.route("/visuals/backlog", methods=["GET"])
def get_backlog_visual():
    try:
        out_format = (request.args.get("format") or "json").lower()
        start_tick, end_tick = _resolve_tick_window(request.args.get("start_tick", type=int), request.args.get("end_tick", type=int))
        with _get_pg_conn() as conn:
            data = get_backlog_data(conn, start_tick, end_tick)
        if out_format == "png":
            fig = build_backlog_figure(data)
            return _figure_png_response(fig)
        return jsonify({"success": True, "data": {"start_tick": start_tick, "end_tick": end_tick, **data}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@cape_bp.route("/visuals/amplification", methods=["GET"])
def get_amplification_visual():
    try:
        out_format = (request.args.get("format") or "json").lower()
        start_tick, end_tick = _resolve_tick_window(request.args.get("start_tick", type=int), request.args.get("end_tick", type=int))
        data = get_amplification_data(start_tick, end_tick)
        if out_format == "png":
            fig = build_amplification_figure(data)
            return _figure_png_response(fig)
        return jsonify({"success": True, "data": {"start_tick": start_tick, "end_tick": end_tick, **data}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@cape_bp.route("/visuals/timeline", methods=["GET"])
def get_timeline_visual():
    try:
        start_tick, end_tick = _resolve_tick_window(request.args.get("start_tick", type=int), request.args.get("end_tick", type=int))
        with _get_pg_conn() as conn:
            data = build_timeline_data(conn, start_tick, end_tick)
        return jsonify({"success": True, "data": {"start_tick": start_tick, "end_tick": end_tick, **data}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@cape_bp.route("/visuals/bullwhip-pro", methods=["GET"])
def get_bullwhip_pro_visual():
    """Interactive bullwhip: scenario vs orders per tick + canonical per-tick RET→DIST amplification."""
    try:
        current_tick = int(r.get("cape:tick:current") or 0)
        latest_tick = max(0, current_tick - 1)
        range_str = request.args.get("range")
        start_tick = request.args.get("start_tick", type=int)
        end_tick = request.args.get("end_tick", type=int)
        s, e = parse_tick_range(range_str, start_tick, end_tick, latest_tick)
        sku = (request.args.get("sku") or "").strip().upper() or None
        with _get_pg_conn() as conn:
            data = get_bullwhip_pro(conn, s, e, sku=sku)
        if str(request.args.get("include_plotly") or "").lower() in ("1", "true", "yes"):
            data = dict(data)
            data["plotly_figure"] = bullwhip_pro_plotly_figure_json(data)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        logger.error(f"CAPE bullwhip-pro failed: {e}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@cape_bp.route("/visuals/capacity-heatmap", methods=["GET"])
def get_capacity_heatmap_visual():
    try:
        current_tick = int(r.get("cape:tick:current") or 0)
        latest_tick = max(0, current_tick - 1)
        range_str = request.args.get("range")
        start_tick = request.args.get("start_tick", type=int)
        end_tick = request.args.get("end_tick", type=int)
        s, e = parse_tick_range(range_str, start_tick, end_tick, latest_tick)
        with _get_pg_conn() as conn:
            data = get_capacity_heatmap(conn, s, e)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        logger.error(f"CAPE capacity-heatmap failed: {e}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@cape_bp.route("/visuals/node-detail", methods=["GET"])
def get_capacity_node_detail():
    try:
        node_id = str(request.args.get("node_id") or "DIST-01")
        tick = request.args.get("tick", type=int)
        if tick is None:
            current_tick = int(r.get("cape:tick:current") or 0)
            tick = max(0, current_tick - 1)
        rcli = get_redis_client()
        with _get_pg_conn() as conn:
            data = get_node_tick_detail(conn, rcli, node_id, int(tick))
        return jsonify({"success": True, "data": data})
    except Exception as e:
        logger.error(f"CAPE node-detail failed: {e}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@cape_bp.route("/visuals/flow-network", methods=["GET"])
def get_flow_network_visual():
    try:
        tick = request.args.get("tick", type=int)
        if tick is None:
            current_tick = int(r.get("cape:tick:current") or 0)
            tick = max(0, current_tick - 1)
        sku = (request.args.get("sku") or "").strip().upper() or None
        with _get_pg_conn() as conn:
            data = get_flow_network(conn, int(tick), sku=sku)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        logger.error(f"CAPE flow-network failed: {e}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@cape_bp.route("/visuals/causality-chain", methods=["GET"])
def get_causality_chain_visual():
    try:
        current_tick = int(r.get("cape:tick:current") or 0)
        latest_tick = max(0, current_tick - 1)
        node_id = request.args.get("node_id")
        range_str = request.args.get("range")
        start_tick = request.args.get("start_tick", type=int)
        end_tick = request.args.get("end_tick", type=int)
        s, e = parse_tick_range(range_str, start_tick, end_tick, latest_tick)
        data = get_causality_payload(node_id, s, e)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        logger.error(f"CAPE causality-chain failed: {e}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@cape_bp.route("/simulate-adjustment", methods=["POST"])
def post_simulate_adjustment():
    """What-if preview: counterfactual metrics + derived chart overlays (no Redis mutation)."""
    try:
        payload = request.get_json() or {}
        sku = str(payload.get("sku") or "").strip().upper() or ""
        demand_pct = float(payload.get("demand_percent", payload.get("percent_change", 0)))
        capacity_relax_pct = float(payload.get("capacity_relax_pct", 0))
        amplification_overlay = float(payload.get("amplification_overlay", 1.0))
        current_tick = int(r.get("cape:tick:current") or 0)
        latest_tick = max(0, current_tick - 1)
        lo = int(payload.get("start_tick", 0))
        hi = int(payload.get("end_tick", latest_tick))
        if hi < lo:
            lo, hi = hi, lo
        hi = min(hi, latest_tick)
        lo = max(0, lo)
        cf = cape_simulate_adjustment(sku, demand_pct, lo, hi)
        with _get_pg_conn() as conn:
            preview = build_whatif_preview(conn, lo, hi, sku, demand_pct, capacity_relax_pct, amplification_overlay)
        return jsonify({"success": True, "data": {"counterfactual": cf, "preview": preview}})
    except Exception as e:
        logger.error(f"CAPE simulate-adjustment failed: {e}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@cape_bp.route("/explore/ask", methods=["POST"])
def explore_ask():
    payload = request.get_json() or {}
    question = payload.get("question", "")
    project_id = payload.get("project_id")
    system_config = payload.get("system_config", {})
    scenario_events = payload.get("scenario_events", [])
    decision_signal = payload.get("decision_signal")
    # Decision-grade path: tool-backed agent (avoid raw redis stream / event-dump answers).
    current_tick = int(r.get("cape:tick:current") or 0)
    try:
        llm_result = _chat_agent.answer(question=question, current_tick=max(0, current_tick - 1))
    except Exception:
        llm_result = {}
    if not isinstance(llm_result, dict) or not llm_result.get("summary"):
        llm_result = build_assistant_response(question, system_config, scenario_events, decision_signal)
    result = _normalize_chat_response(llm_result)
    if project_id:
        _append_project_chat(project_id, question, result)
    return jsonify({"success": True, "data": result})


@cape_bp.route("/projects/save", methods=["POST"])
def save_project():
    payload = request.get_json() or {}
    project_name = str(payload.get("project_name") or "").strip() or "Untitled Supply Chain Project"
    system_config = payload.get("system_config") or {}
    scenario_events = normalize_scenario_rows(payload.get("scenario_events") or [])
    scenario_file_name = str(payload.get("scenario_file_name") or "")
    errors = validate_system_config(system_config)
    if errors:
        return jsonify({"success": False, "error": "Invalid system_config", "errors": errors}), 400
    project_id = str(payload.get("project_id") or f"scproj-{int(time.time() * 1000)}")
    apply_schema_migrations()
    _persist_project(project_id, project_name, system_config, scenario_events, scenario_file_name)
    return jsonify({"success": True, "data": {"project_id": project_id, "project_name": project_name}})


@cape_bp.route("/projects/history", methods=["GET"])
def list_projects_history():
    try:
        apply_schema_migrations()
        with _get_pg_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    project_id,
                    project_name,
                    scenario_file_name,
                    latest_status,
                    latest_visual_summary,
                    created_at,
                    updated_at,
                    last_run_at
                FROM cape_projects
                ORDER BY updated_at DESC
                LIMIT 50
                """
            )
            rows = cur.fetchall()
        history = [
            {
                "project_id": row[0],
                "project_name": row[1],
                "scenario_file_name": row[2] or "",
                "latest_status": row[3] or "draft",
                "latest_visual_summary": row[4] or {},
                "created_at": row[5].isoformat() if row[5] else None,
                "updated_at": row[6].isoformat() if row[6] else None,
                "last_run_at": row[7].isoformat() if row[7] else None,
            }
            for row in rows
        ]
        return jsonify({"success": True, "data": {"projects": history}})
    except Exception as e:
        logger.exception("list_projects_history failed")
        return jsonify({"success": False, "error": str(e)}), 500


@cape_bp.route("/projects/<project_id>", methods=["GET"])
def get_project(project_id: str):
    apply_schema_migrations()
    with _get_pg_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                project_id,
                project_name,
                scenario_file_name,
                system_config,
                scenario_events,
                latest_status,
                latest_decision,
                latest_metrics,
                latest_visual_summary,
                latest_report,
                chat_history
            FROM cape_projects
            WHERE project_id = %s
            LIMIT 1
            """,
            (project_id,),
        )
        row = cur.fetchone()
    if not row:
        return jsonify({"success": False, "error": "Project not found"}), 404
    return jsonify(
        {
            "success": True,
            "data": {
                "project_id": row[0],
                "project_name": row[1],
                "scenario_file_name": row[2] or "",
                "system_config": row[3] or {},
                "scenario_events": row[4] or [],
                "latest_status": row[5] or "draft",
                "latest_decision": row[6] or {},
                "latest_metrics": row[7] or {},
                "latest_visual_summary": row[8] or {},
                "latest_report": row[9] or {},
                "chat_history": row[10] or [],
            },
        }
    )


@cape_bp.route("/projects/<project_id>/report/snapshot", methods=["POST"])
def save_project_report_snapshot(project_id: str):
    payload = request.get_json() or {}
    report = payload.get("report") or {}
    apply_schema_migrations()
    _save_project_report(project_id, report)
    return jsonify({"success": True, "data": {"project_id": project_id}})


@cape_bp.route("/projects/<project_id>/chat", methods=["POST"])
def save_project_chat(project_id: str):
    payload = request.get_json() or {}
    question = str(payload.get("question") or "").strip()
    answer = payload.get("answer") or {}
    if not question:
        return jsonify({"success": False, "error": "question is required"}), 400
    apply_schema_migrations()
    _append_project_chat(project_id, question, answer)
    return jsonify({"success": True, "data": {"project_id": project_id}})
