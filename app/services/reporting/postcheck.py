"""Step 15 – post-cleaning validation and before/after comparison."""
from __future__ import annotations

from app.services.common.banking_rules import RULES
from app.services.common.checks import compute_mask
from app.services.common.io_utils import jsonable
from app.services.analysis.validation import run_initial_validation


def _key(i):
    return (i["column"], i["issue_type"], (i.get("params") or {}).get("other"))


def post_validate(cleaned, col_of: dict, before_issues: list, approved: list, rows_before: int,
                   unmapped_columns: set[str] | None = None) -> dict:
    after = run_initial_validation(cleaned, col_of)
    # "Unknown" is the intentional missing-value marker for generic unmapped text
    # columns. Do not report that deliberate marker as an unresolved placeholder.
    unmapped_columns = unmapped_columns or set()
    filtered = []
    for issue in after["issues"]:
        col = issue.get("column")
        if col in unmapped_columns and issue.get("issue_type") == "placeholder":
            s = cleaned[col].astype("string").str.strip().str.lower()
            unknown_count = int(s.eq("unknown").sum())
            if unknown_count >= int(issue.get("affected_rows", 0)):
                continue
        filtered.append(issue)
    after["issues"] = filtered
    after["issues_after"] = len(filtered)
    bmap = {_key(i): i["affected_rows"] for i in before_issues}
    amap = {_key(i): i["affected_rows"] for i in after["issues"]}
    table = []
    for k in list(bmap) + [k for k in amap if k not in bmap]:
        b, a = bmap.get(k, 0), amap.get(k, 0)
        status = "resolved" if a == 0 else "improved" if a < b else "unchanged" if a == b else "worse"
        table.append({"column": k[0], "issue_type": k[1], "before": b, "after": a, "status": status})

    constraints = []
    for rec in approved:
        if rec["action"] == "flag_only" or not rec.get("column"):
            if rec["action"] == "drop_duplicate_rows":
                pass
            else:
                continue
        try:
            remaining = int(compute_mask(cleaned, rec.get("column"), rec["issue_type"],
                                         RULES.get(rec.get("canonical"), {}), rec.get("issue_params") or {}).sum())
        except Exception as e:  # noqa: BLE001
            constraints.append({"rec_id": rec["rec_id"], "column": rec.get("column"), "issue_type": rec["issue_type"],
                                "action": rec["action"], "remaining": None, "satisfied": None, "note": str(e)})
            continue
        constraints.append({"rec_id": rec["rec_id"], "column": rec.get("column"), "issue_type": rec["issue_type"],
                            "action": rec["action"], "remaining": remaining, "satisfied": remaining == 0})
    return jsonable({
        "rows_before": rows_before, "rows_after": len(cleaned),
        "issues_before": len(before_issues), "issues_after": len(after["issues"]),
        "comparison": table, "approved_constraints": constraints,
        "remaining_issues": after["issues"], "engine_notes": after["engine_notes"],
    })
