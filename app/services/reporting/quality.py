"""Honest statuses, fixed-threshold outlier recount, per-column comparison, quality score, manual-review list."""
from __future__ import annotations

import html
from collections import defaultdict

from app.services.common.checks import compute_mask

WEIGHT = {"error": 1.0, "warning": 0.5, "info": 0.2}
E = html.escape


def _status(before, after):
    return ("resolved" if after == 0 else "improved" if after < before
            else "unchanged" if after == before else "worse")


def fix_log_status(log: list) -> list:
    out = []
    for e in log:
        e = dict(e)
        if e.get("action") == "flag_only":
            e["status"] = "flagged"
        elif e.get("status") in ("verified", "applied") and int(e.get("affected_rows") or 0) == 0:
            e["status"] = "no_change"
            e["note"] = (str(e.get("note") or "") + " | no rows changed").strip(" |")
        out.append(e)
    return out


def recount_outliers(cleaned, comparison: list, before_issues: list) -> list:
    by = {(i.get("column"), i["issue_type"]): i for i in before_issues}
    out = []
    for row in comparison:
        row = dict(row)
        if row.get("issue_type") == "outlier":
            p = (by.get((row.get("column"), "outlier")) or {}).get("params") or {}
            if "lo" in p and "hi" in p and row.get("column") in cleaned.columns:
                try:
                    n = int(compute_mask(cleaned, row["column"], "outlier", {}, p).sum())
                    row.update(after=n, status=_status(row["before"], n), note="same thresholds as before")
                except Exception:  # noqa: BLE001
                    pass
            elif row.get("status") == "worse":
                row.update(status="not_comparable", note="thresholds recomputed after cleaning")
        out.append(row)
    return out


def column_comparison(comparison: list) -> list:
    g = defaultdict(lambda: {"issue_types": [], "before": 0, "after": 0})
    for r in comparison:
        k = r.get("column") or "(whole dataset)"
        g[k]["issue_types"].append(r["issue_type"])
        g[k]["before"] += int(r.get("before") or 0)
        g[k]["after"] += int(r.get("after") or 0)
    return [{"column": k, **v} for k, v in sorted(g.items(), key=lambda kv: -kv[1]["before"])]


def quality_score(issues: list, n_rows: int, n_cols: int) -> float:
    if n_rows <= 0:
        return 0.0
    per, ds = defaultdict(float), 0.0
    for i in issues:
        pen = WEIGHT.get(i.get("severity"), 0.5) * int(i.get("affected_rows") or 0) / n_rows
        if i.get("column"):
            per[i["column"]] += pen
        else:
            ds += pen
    col_pen = sum(min(1.0, v) for v in per.values()) / max(n_cols, 1)
    return round(100 * (1 - min(1.0, col_pen + ds)), 1)


def _verdict(score):
    return "Good" if score >= 90 else "Needs review" if score >= 70 else "Poor"


def build_summary(before_issues, post, decisions, rows_before, rows_after, n_cols) -> dict:
    remaining = post.get("remaining_issues", [])
    sb = quality_score(before_issues, rows_before, n_cols)
    sa = quality_score(remaining, rows_after, n_cols)
    manual, seen = [], set()
    for d in decisions:
        if d["decision"] == "reject" or d["action"] == "flag_only":
            why = "rejected by user" if d["decision"] == "reject" else "no automatic fix (flag only)"
            manual.append({"column": d.get("column"), "issue_type": d["issue_type"],
                           "rows": d.get("affected_rows"), "reason": why})
            seen.add((d.get("column"), d["issue_type"]))
    for i in remaining:
        if (i.get("column"), i["issue_type"]) not in seen:
            manual.append({"column": i.get("column"), "issue_type": i["issue_type"],
                           "rows": i["affected_rows"], "reason": "still present after cleaning"})
    dropped = round(100 * (rows_before - rows_after) / max(rows_before, 1), 2)
    return {"score_before": sb, "score_after": sa, "verdict": _verdict(sa), "rows_dropped_pct": dropped,
            "rows_before": rows_before, "rows_after": rows_after,
            "columns": column_comparison(post.get("comparison", [])), "manual_review": manual}


def quality_html(q: dict) -> str:
    def card(l, v, n=""):
        return (f'<div class="card"><div class="card-label">{E(l)}</div><div class="card-value">{E(str(v))}</div>'
                f'<div class="card-note">{E(n)}</div></div>')

    def items(rows):
        return "".join(f'<div class="item"><span>{E(a)}</span><strong>{E(b)}</strong></div>' for a, b in rows) \
            or '<div class="item"><span>None</span><strong>-</strong></div>'

    cards = (card("Quality score before", q["score_before"], "out of 100")
             + card("Quality score after", q["score_after"], q["verdict"])
             + card("Rows dropped", f'{q["rows_dropped_pct"]}%', f'{q["rows_before"]} to {q["rows_after"]}')
             + card("Needs manual review", len(q["manual_review"]), "issues not fixed"))
    cols = items([(c["column"], f'{c["before"]} to {c["after"]}  ({", ".join(c["issue_types"])})')
                  for c in q["columns"]])
    man = items([(f'{m["column"] or "dataset"}: {m["issue_type"]}', f'{m["rows"]} rows - {m["reason"]}')
                 for m in q["manual_review"]])
    return (f'<h2>Data quality score</h2><div class="metrics">{cards}</div>'
            f'<h2>Comparison by column</h2><div class="section">{cols}</div>'
            f'<h2>Needs manual review</h2><div class="section">{man}</div>')