"""Block obviously inconsistent chat outputs before they reach the client."""

from __future__ import annotations

import re


def validate_output(question: str, bundle: dict, response: dict) -> tuple[bool, list[str]]:
    errs: list[str] = []
    q = (question or "").strip()
    met = bundle.get("metrics") or {}
    fd = bundle.get("flow_diagram") or {}
    stages = fd.get("stages") or []
    em = met.get("edge_metrics") or {}
    ledger_edges_hot = any((isinstance(v, dict) and (int(v.get("orders") or 0) > 0 or int(v.get("demand") or 0) > 0)) for v in em.values())

    if stages and ledger_edges_hot:
        dead = all(
            (int(s.get("demand") or 0) == 0 and int(s.get("order") or 0) == 0 and int(s.get("backlog") or 0) == 0)
            for s in stages
        )
        if dead:
            errs.append("flow_diagram_all_zero_while_edge_metrics_nonzero")

    rc = bundle.get("root_cause") or {}
    sku_hint = (bundle.get("question_scope") or {}).get("sku_hint")
    if sku_hint and str(rc.get("sku") or "").upper() == "UNKNOWN" and re.search(rf"\b{re.escape(str(sku_hint))}\b", q, re.I):
        errs.append("question_mentions_sku_but_chain_sku_unknown")

    bl = int(met.get("backlog") or 0)
    summary = str(response.get("summary") or "")
    if bl > 100 and re.search(r"backlog\s*=\s*0\b|no backlog|zero backlog", summary, re.I):
        errs.append("summary_backlog_zero_conflicts_metrics")

    return (len(errs) == 0, errs)
