"""Step 12 – AI cleaning recommendations (rule baseline + history + Qwen refinement)."""
from __future__ import annotations

import pandas as pd

from app.core.config import settings
from app.services.common.banking_rules import RULES, UNKNOWN_FIELDS
from app.services.common.checks import col_kind
from app.services.ai.history import rec_key
from app.services.common.io_utils import jsonable
from app.services.ai.llm import ask_json
from app.services.actions.tools import category_map

ALLOWED = {
    "missing": ["fill_missing", "drop_rows", "flag_only"],
    "placeholder": ["placeholder_to_null", "flag_only"],
    "whitespace": ["strip_whitespace", "flag_only"],
    "case_inconsistency": ["unify_case", "flag_only"],
    "duplicate_values": ["drop_duplicates_on_column", "flag_only"],
    "duplicate_rows": ["drop_duplicate_rows", "flag_only"],
    "invalid_type": ["coerce_type", "drop_rows", "flag_only"],
    "out_of_range": ["set_null", "clip_range", "drop_rows", "flag_only"],
    "invalid_format": ["fix_format_or_null", "set_null", "drop_rows", "flag_only"],
    "invalid_value": ["map_to_allowed_or_null", "set_null", "drop_rows", "flag_only"],
    "outlier": ["flag_only", "cap_outliers", "set_null"],
    "future_date": ["set_null", "drop_rows", "flag_only"],
    "cross_column": ["flag_only", "drop_rows", "set_null"],
    "missing": ["fill_unknown", "fill_missing", "drop_rows", "flag_only"],
    "numeric_text": ["parse_money", "flag_only"],
    "name_format": ["fix_names", "flag_only"],
    "category_variant": ["merge_categories", "flag_only"],
    "sentinel": ["sentinel_to_null", "flag_only"],
    "date_format": ["parse_dates", "flag_only"],
}
ALL_ACTIONS = sorted({a for v in ALLOWED.values() for a in v})

DROP_ACTIONS = {"drop_rows", "drop_duplicates_on_column", "drop_duplicate_rows"}
MAX_DROP_PCT = 5.0


def _guard(issue, action, params, reason, n):
    pct = issue.get("affected_pct") or round(100 * issue["affected_rows"] / max(n, 1), 2)
    if action in DROP_ACTIONS and pct > MAX_DROP_PCT:
        msg = (f"Dropping would remove {pct}% of rows (limit {MAX_DROP_PCT}%). Flagged for your decision; "
               f"change the action to a drop only if you accept the data loss.")
        return "flag_only", {}, msg, pct, True
    return action, params, reason, pct, False

RISK = {
    "fill_missing": "Imputed values are estimates and may bias statistics.",
    "drop_rows": "Rows are permanently removed from the cleaned dataset.",
    "flag_only": "No data changed; the issue remains.",
    "placeholder_to_null": "Low risk; placeholders become empty values.",
    "strip_whitespace": "Very low risk.",
    "unify_case": "Low risk; values map to their most common spelling.",
    "drop_duplicates_on_column": "Later rows sharing the same key are removed; verify they are true duplicates.",
    "drop_duplicate_rows": "Exact duplicate rows are removed (first kept).",
    "coerce_type": "Values that cannot be parsed become empty.",
    "set_null": "Offending values are blanked, losing the original value.",
    "clip_range": "Values are altered to the nearest allowed bound.",
    "fix_format_or_null": "Auto-fixed values are normalised; unfixable ones become empty.",
    "map_to_allowed_or_null": "Unrecognised values become empty.",
    "cap_outliers": "Extreme but possibly genuine values are capped.",
    "fill_unknown": "Missing values become the text 'Unknown'; real data is not recovered.",
    "parse_money": "Column becomes numeric; unreadable values become empty.",
    "fix_names": "Names are reordered (Last, First to First Last) and capitalised.",
    "merge_categories": "Variants are merged into the most common spelling; check the merges.",
    "sentinel_to_null": "Dummy values become empty; rows then follow the missing-value action.",
    "parse_dates": "Dates become real dates (day first when ambiguous); unreadable values become empty.",
}

ACTION_DOC = {
    "fill_missing": "params.strategy: median|mean|mode|constant(+value)", "drop_rows": "remove violating rows",
    "flag_only": "do nothing", "placeholder_to_null": "N/A/null/- -> empty", "strip_whitespace": "trim spaces",
    "unify_case": "most common spelling", "drop_duplicates_on_column": "drop repeated key rows",
    "drop_duplicate_rows": "drop exact duplicate rows", "coerce_type": "convert to numeric/date",
    "set_null": "blank violating values", "clip_range": "clip to min/max", "fix_format_or_null": "normalise or blank",
    "map_to_allowed_or_null": "map to allowed list or blank", "cap_outliers": "winsorise by IQR",
    "fill_unknown": "replace missing with 'Unknown'", "parse_money": "convert to numeric", "fix_names": "reorder and capitalise",
    "merge_categories": "merge variants into most common spelling",
    "sentinel_to_null": "dummy values like 2099-01-01 / 999 -> empty",
    "parse_dates": "text -> real date",
}


def _baseline(issue: dict, kind: str, rule: dict):
    t, rate = issue["issue_type"], (issue.get("affected_pct") or 0)
    canon = issue.get("canonical")
    params = {}
    if t == "missing":
        if canon in UNKNOWN_FIELDS or (not canon and kind == "text"):
            action = "fill_unknown"
        elif rule.get("required") and rate <= 30:
            action = "drop_rows"
        elif rule.get("required"):
            action = "flag_only"
        elif kind == "numeric":
            action, params = "fill_missing", {"strategy": "median"}
        elif kind == "category":
            action, params = "fill_missing", {"strategy": "mode"}
        else:
            action = "flag_only"
    else:
        action = {
            "placeholder": "placeholder_to_null", "whitespace": "strip_whitespace",
            "case_inconsistency": "unify_case", "duplicate_values": "drop_duplicates_on_column",
            "duplicate_rows": "drop_duplicate_rows", "invalid_type": "coerce_type", "out_of_range": "set_null",
            "invalid_format": "fix_format_or_null", "invalid_value": "map_to_allowed_or_null",
            "outlier": "flag_only", "future_date": "set_null", "cross_column": "flag_only",
            "numeric_text": "parse_money", "name_format": "fix_names", "category_variant": "merge_categories",
            "sentinel": "sentinel_to_null",
            "date_format": "parse_dates"
        }[t]
    reason = (f"{issue['affected_rows']} row(s) in '{issue['column'] or 'dataset'}' have "
              f"{t.replace('_', ' ')}; '{action}' is the standard fix.")
    return action, params, reason

def build_recommendations(df: pd.DataFrame, issues: list, hints: dict):
    recs = []
    for n, issue in enumerate(issues, 1):
        t = issue["issue_type"]
        if t not in ALLOWED:
            continue
        canon, col = issue.get("canonical"), issue.get("column")
        rule = RULES.get(canon, {})
        kind = col_kind(df, col, canon) if col in df.columns else "text"
        action, params, reason = _baseline(issue, kind, rule)
        key = rec_key(canon, col, t)
        h = hints.get(key)
        source, locked = "baseline", False
        if h and h.get("preferred_action") in ALLOWED[t] and h["approved"] > h["rejected"]:
            if h["preferred_action"] != action:
                action, params = h["preferred_action"], ({"strategy": "median"} if h["preferred_action"] == "fill_missing" and kind == "numeric" else {})
            source, locked = "history", h["approved"] >= h["rejected"] + 2
            reason += f" Previously approved {h['approved']} time(s)."
        if t == "category_variant" and h and h.get("params"):
            params = h["params"]
        preview = category_map(df[col], col, params) if (t == "category_variant" and col in df.columns) else None        
        action, params, reason, pct, guarded = _guard(issue, action, params, reason, len(df))
        recs.append({
            "id": f"REC-{n:03d}", "issue_id": issue["id"], "column": col, "canonical": canon, "issue_type": t,
            "issue_params": issue.get("params") or {}, "action": action, "params": params, "reason": reason,
            "risk": RISK[action], "affected_rows": issue["affected_rows"], "affected_pct": issue.get("affected_pct"),
            "allowed_actions": ALLOWED[t], "history_hint": h, "source": source, "_locked": locked, "key": key,
            "_samples": issue.get("sample_values", [])[:3],
            "data_loss_pct": pct, "guarded": guarded,
            "preview": preview,
        })

    # Qwen refinement (action must stay inside the allowed list)
    items = [{"issue_id": r["issue_id"], "column": r["column"], "canonical": r["canonical"],
              "issue_type": r["issue_type"], "affected_rows": r["affected_rows"], "samples": r["_samples"],
              "baseline_action": r["action"], "allowed_actions": r["allowed_actions"],
              "history": r["history_hint"]} for r in sorted(recs, key=lambda r: -r["affected_rows"])[:20]]
    err = None
    if items and settings.llm_enabled and settings.enable_ai_recommendations:
        data, err = ask_json(
            "You are a banking data-cleaning advisor. For each issue choose the best action from allowed_actions "
            "(prefer baseline_action unless clearly wrong, respect history), give a short reason and the main risk. "
            'Return {"recommendations":[{"issue_id":"...","action":"...","reason":"...","risk":"..."}]}.',
            {"issues": items, "action_guide": ACTION_DOC})
        by_issue = {r["issue_id"]: r for r in recs}
        for x in (data or {}).get("recommendations", []) or []:
            r = by_issue.get(x.get("issue_id"))
            if not r:
                continue
            if x.get("action") in r["allowed_actions"] and not r["_locked"]:
                if x["action"] != r["action"]:
                    r["params"] = {"strategy": "median"} if x["action"] == "fill_missing" else {}
                r["action"] = x["action"]
                r["source"] = "ai" if r["source"] == "baseline" else r["source"]
            if x.get("reason"):
                r["reason"] = str(x["reason"])[:400]
            r["risk"] = str(x["risk"])[:300] if x.get("risk") else RISK[r["action"]]
    for r in recs:
        if r["action"] in DROP_ACTIONS and r["data_loss_pct"] > MAX_DROP_PCT:
            r["action"], r["params"], r["guarded"] = "flag_only", {}, True
            r["risk"] = RISK["flag_only"]
            r["reason"] = (f"Dropping would remove {r['data_loss_pct']}% of rows (limit {MAX_DROP_PCT}%). "
                           f"Flagged for your decision.")
        r.pop("_locked", None)
        r.pop("_samples", None)
    return jsonable(recs), err
