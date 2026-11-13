"""Step 8 – prepare compact AI context."""
from __future__ import annotations

from app.services.common.io_utils import jsonable


def build_context(inspection: dict, col_of: dict, profile: dict, issues: list, hints: dict) -> dict:
    canon_of = {v: k for k, v in col_of.items()}
    cols = []
    for c in profile["columns"][:40]:
        item = {k: c.get(k) for k in ("name", "kind", "dtype", "missing_pct", "unique")}
        item["canonical"] = canon_of.get(c["name"])
        for k in ("min", "max", "mean", "median"):
            if k in c:
                item[k] = round(c[k], 3)
        item["top_values"] = list(c.get("top_values", {}).items())[:4]
        if c.get("top_patterns"):
            item["top_patterns"] = list(c["top_patterns"].items())[:3]
        if c.get("unusual"):
            item["unusual"] = c["unusual"][:3]
        cols.append(item)
    keep = [c["name"] for c in cols][:20]
    samples = [{k: v for k, v in row.items() if k in keep} for row in inspection["samples"]["head"][:3]]
    ctx = {
        "dataset": {"rows": profile["rows"], "columns": profile["column_count"],
                    "duplicate_rows": profile["duplicate_rows"]},
        "columns": cols,
        "existing_issues": [{"id": i["id"], "column": i["column"], "type": i["issue_type"],
                             "rows": i["affected_rows"], "severity": i["severity"]} for i in issues[:30]],
        "samples": samples,
        "correlated_pairs": profile.get("correlations", [])[:5],
        "historical_banking_knowledge": dict(list(hints.items())[:10]),
    }
    return jsonable(ctx)
