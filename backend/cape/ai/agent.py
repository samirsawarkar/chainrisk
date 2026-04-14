from __future__ import annotations

import json
import logging

from app.utils.llm_client import LLMClient
from cape.ai.output_validation import validate_output
from cape.ai.prompt_builder import apply_question_rules, build_dynamic_context, build_system_prompt
from cape.ai.tools import collect_tool_bundle, get_causality_chain, get_metrics, get_root_cause
from cape.visuals.chat_visuals import (
    build_backlog_chart,
    build_bullwhip_chart,
    build_capacity_chart,
    build_flow_diagram,
)


logger = logging.getLogger(__name__)


class CAPEChatAgent:
    def __init__(self):
        self._llm = None
        try:
            self._llm = LLMClient()
        except Exception:
            self._llm = None

    def _decision_grade_from_bundle(self, bundle: dict, current_tick: int) -> dict:
        """Always grounded in get_metrics + get_root_cause (ledger + scenario)."""
        t = max(0, int(current_tick))
        m = bundle.get("metrics") or get_metrics(t)
        node = (bundle.get("question_scope") or {}).get("node_id")
        tr_list = (bundle.get("question_scope") or {}).get("tick_range") or [0, t]
        tr = (int(tr_list[0]), int(tr_list[-1]))
        rc = bundle.get("root_cause") or get_root_cause(node, tr[1], tr[0])
        chain_lines = get_causality_chain(node, tr)
        top = (bundle.get("sku_impact") or [{}])[0] if bundle.get("sku_impact") else {}
        dist_peak = float(rc.get("dist_amplification_vs_ret") or (bundle.get("bullwhip_chain") or {}).get("dist_over_ret_peak") or 1.0)
        sku = rc.get("sku") or m.get("spike_sku") or top.get("sku_id") or "UNKNOWN"
        trigger_node = rc.get("trigger_node") or "DIST-01"
        tt = rc.get("trigger_tick", tr[1])
        cap_u = float(rc.get("capacity_util_pct") or 0.0)
        mw = m.get("metric_window") or tr_list
        sp_from = int(m.get("spike_from") or 0)
        sp_to = int(m.get("spike_to") or 0)

        summary = (
            f"{trigger_node} reached {cap_u:.1f}% utilization at T{tt} within T{mw[0]}–T{mw[-1]}, led by SKU {sku} "
            f"(metrics window; scenario spike marker {sp_from}→{sp_to}) with canonical RET→DIST amplification {dist_peak:.2f}×."
        )
        evidence = [
            f"system_backlog={m['backlog']} units at T{m['tick']}",
            f"instability_index={m['instability']:.3f} (window T{mw[0]}–T{mw[-1]})",
            f"RET→DIST_amplification={dist_peak:.2f}×",
            f"{trigger_node}_utilization={cap_u:.1f}%",
        ]
        if sp_to > 0 or sp_from > 0:
            evidence.append(f"scenario_spike SKU {m.get('spike_sku') or sku}: {sp_from}→{sp_to}")
        if top:
            evidence.append(
                f"SKU {top.get('sku_id')}: scenario_demand_sum={top.get('demand')} RET_orders={top.get('retailer_orders')}"
            )
        if m.get("metric_anomalies"):
            evidence.append(f"anomalies={len(m['metric_anomalies'])} flags (see tool_context.metrics.metric_anomalies)")
        causal = [rc.get("chain_roles") or "RET → DIST → MFG → SUP"]
        causal.extend([c for c in chain_lines if c and c not in causal])
        decision = f"Reduce {sku} retail-facing pressure 10–15% or add short-term capacity at {trigger_node} before T{int(tt or tr[1]) + 2}."
        cf = bundle.get("counterfactual") or {}
        if cf:
            impact = [
                f"counterfactual backlog Δ (model): {cf.get('backlog_change')} units",
                f"counterfactual instability Δ (model): {cf.get('instability_change')}",
            ]
        else:
            impact = [
                f"observed backlog at T{m['tick']}: {m['backlog']} units",
                f"observed window instability_index: {m['instability']:.3f}",
            ]
        return {
            "summary": summary,
            "direct_answer": summary,
            "evidence": evidence,
            "causal_chain": causal,
            "impact": impact,
            "decision": decision,
        }

    def _merge_llm(self, base: dict, llm: dict) -> dict:
        if not isinstance(llm, dict):
            return base
        out = dict(base)
        for k in ("summary", "decision", "direct_answer"):
            v = str(llm.get(k, "") or "").strip()
            if len(v) > 12 and any(ch.isdigit() for ch in v):
                out[k] = v
        if str(out.get("direct_answer", "")).strip() == "":
            out["direct_answer"] = out.get("summary", "")
        ev = llm.get("evidence")
        if isinstance(ev, list) and len(ev) >= 2:
            out["evidence"] = [str(x) for x in ev[:6]]
        cc = llm.get("causal_chain")
        if isinstance(cc, list) and cc:
            out["causal_chain"] = [str(x) for x in cc[:8]]
        elif isinstance(cc, str) and cc.strip():
            out["causal_chain"] = [cc.strip()]
        imp = llm.get("impact")
        if isinstance(imp, list) and len(imp) >= 1:
            out["impact"] = [str(x) for x in imp[:4]]
        return out

    def answer(self, question: str, current_tick: int) -> dict:
        bundle = collect_tool_bundle(question=question, current_tick=current_tick)
        rules = apply_question_rules(question)

        base = self._decision_grade_from_bundle(bundle, current_tick)

        llm_output = None
        if self._llm is not None:
            messages = [
                {"role": "system", "content": build_system_prompt()},
                {"role": "user", "content": build_dynamic_context(question, bundle)},
            ]
            try:
                llm_output = self._llm.chat_json(messages=messages, temperature=0.0, max_tokens=1400)
            except Exception:
                llm_output = None

        if isinstance(llm_output, dict) and str(llm_output.get("summary", "")).strip():
            merged = self._merge_llm(base, llm_output)
        else:
            merged = base

        ok, val_errs = validate_output(question, bundle, merged)
        if not ok:
            logger.error("cape_output_validation_failed %s", val_errs)
            chain = (bundle.get("root_cause") or {}).get("chain") or []
            merged["summary"] = (
                f"[blocked: {', '.join(val_errs)}] " + (str(chain[0]) if chain else "Inspect tool_context.metrics and flow_diagram.")
            )
            merged["direct_answer"] = merged["summary"]
            merged["evidence"] = [str(x) for x in chain[:6]] if chain else merged.get("evidence", [])

        charts = []
        if rules["include_bullwhip"]:
            charts.append(build_bullwhip_chart(bundle.get("visuals") or {}))
        if rules["include_capacity"]:
            charts.append(build_capacity_chart(bundle.get("visuals") or {}))
        if rules["include_backlog"]:
            charts.append(build_backlog_chart(bundle.get("visuals") or {}))

        diagram = build_flow_diagram(bundle.get("flow_diagram") or {})
        return {
            "direct_answer": str(merged.get("direct_answer") or merged.get("summary", "")),
            "summary": str(merged.get("summary", "")),
            "evidence": merged.get("evidence") or [],
            "causal_chain": merged.get("causal_chain") or [],
            "impact": merged.get("impact") or [],
            "decision": str(merged.get("decision", "")),
            "charts": charts,
            "diagram": diagram,
            "tool_context": json.loads(json.dumps(bundle)),
        }
