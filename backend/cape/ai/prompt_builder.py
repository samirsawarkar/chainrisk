from __future__ import annotations

import json


def build_system_prompt() -> str:
    return (
        "You are a CAPE supply-chain decision analyst. "
        "You MUST only use numbers, SKU ids, and node ids that appear in the tool JSON. "
        "Never invent quantities. Every sentence must cite at least one numeric fact from the bundle. "
        "Respect question_scope.tick_range: do not cite ticks outside that window unless tool_context marks a nearest-tick note. "
        "Amplification MUST match tool_context.metrics.amplification (canonical edge formula); do not recompute. "
        "Output JSON with keys: summary (one sentence, same as direct_answer), direct_answer (one sentence), "
        "evidence (array of short strings each containing a number), "
        "causal_chain (array, first item must be 'RET → DIST → MFG → SUP' or a variant with the same nodes), "
        "impact (array of two short strings: backlog effect, instability/amplification effect), "
        "decision (one imperative line with SKU and node)."
    )


def build_dynamic_context(question: str, tool_bundle: dict) -> str:
    return (
        f"Question:\n{question}\n\n"
        f"Tool data (JSON; metrics and root_cause are authoritative):\n{json.dumps(tool_bundle, ensure_ascii=False)}\n\n"
        "The bundle already includes metrics, root_cause, sku_impact, bullwhip_chain, and flow_diagram. "
        "Reuse those values verbatim where possible. "
        "Respond as JSON only with keys: summary, direct_answer, evidence, causal_chain, impact, decision."
    )


def apply_question_rules(question: str) -> dict:
    q = (question or "").lower()
    include_bullwhip = any(k in q for k in ("bullwhip", "amplification", "dist", "mfg", "capacity", "100%"))
    include_capacity = any(k in q for k in ("capacity", "utilization", "bottleneck", "100%"))
    include_backlog = any(k in q for k in ("backlog", "delay", "late", "queue"))
    return {
        "include_bullwhip": include_bullwhip or not (include_capacity or include_backlog),
        "include_capacity": include_capacity or not (include_bullwhip or include_backlog),
        "include_backlog": include_backlog,
    }
