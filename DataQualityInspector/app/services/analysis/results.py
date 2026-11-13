"""Step 11 – consolidated quality results."""
from __future__ import annotations

from collections import Counter

from app.services.common.io_utils import jsonable


def consolidate(issues: list, verified: list, interpretations: list, llm_error, engine_notes: dict) -> dict:
    ai_issues, confirmed, unverified = [], [], []
    for v in verified:
        if v["status"] == "Confirmed":
            confirmed.append(v)
            if not v.get("duplicate_of"):
                ai_issues.append({
                    "id": v["id"], "column": v["column"], "canonical": v.get("canonical"),
                    "issue_type": v["issue_type"], "severity": "warning",
                    "description": f"[AI verified] {v['description']} ({v['affected_rows']} rows)",
                    "affected_rows": v["affected_rows"], "affected_pct": None,
                    "sample_rows": v["sample_rows"], "sample_values": v["sample_values"],
                    "sources": ["qwen3_verified"], "params": v["params"],
                })
        else:
            unverified.append(v)
    all_issues = list(issues) + ai_issues
    summary = {
        "total_issues": len(all_issues),
        "rule_engine_issues": len(issues),
        "ai_verified_new_issues": len(ai_issues),
        "by_severity": dict(Counter(i["severity"] for i in all_issues)),
        "ai_finding_status": dict(Counter(v["status"] for v in verified)),
    }
    return jsonable({"summary": summary, "issues": all_issues, "verified_ai_findings": confirmed,
                     "unverified_ai_suggestions": unverified, "ai_interpretations": interpretations,
                     "llm_error": llm_error, "engine_notes": engine_notes})
