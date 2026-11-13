"""Step 10 – generic Python validation engine verifying AI findings against all rows."""
from __future__ import annotations

import re

from app.services.common.banking_rules import RULES
from app.services.common.checks import OPS, compute_mask
from app.services.common.io_utils import jsonable

METHOD_TO_ISSUE = {
    "null_check": "missing", "placeholder_check": "placeholder", "whitespace_check": "whitespace",
    "case_inconsistency": "case_inconsistency", "duplicate_values": "duplicate_values",
    "duplicate_rows": "duplicate_rows", "non_numeric": "invalid_type", "unparseable_date": "invalid_type",
    "numeric_range": "out_of_range", "regex_mismatch": "invalid_format", "allowed_values": "invalid_value",
    "outlier_iqr": "outlier", "future_date": "future_date", "cross_column_compare": "cross_column",
}


def _result(f, status, note, issue_type=None, params=None, affected=0, rows=None, samples=None, extra=None):
    out = {**f, "status": status, "note": note, "issue_type": issue_type, "params": params or f.get("params", {}),
           "affected_rows": affected, "sample_rows": rows or [], "sample_values": samples or []}
    if extra:
        out.update(extra)
    return out


def verify_finding(df, f: dict, col_of: dict, existing_issues: list) -> dict:
    canon_of = {v: k for k, v in col_of.items()}
    method, col, params = f.get("method"), f.get("column"), dict(f.get("params") or {})
    if f.get("needs_business_context"):
        return _result(f, "Context required", "Needs business context that is not available in the data")
    if method not in METHOD_TO_ISSUE:
        return _result(f, "Unsupported", f"Method '{method}' is not supported by the validation engine")
    t = METHOD_TO_ISSUE[method]
    if method == "non_numeric":
        params["kind"] = "numeric"
    if method == "unparseable_date":
        params["kind"] = "date"
    if t != "duplicate_rows" and col not in df.columns:
        return _result(f, "Cannot verify", f"Column '{col}' not found", t, params)

    # parameter sanity
    if t == "out_of_range":
        try:
            for k in ("min", "max"):
                if params.get(k) is not None:
                    params[k] = float(params[k])
        except (TypeError, ValueError):
            return _result(f, "Cannot verify", "min/max must be numeric", t, params)
        if params.get("min") is None and params.get("max") is None:
            return _result(f, "Cannot verify", "No min/max supplied", t, params)
    if t == "invalid_format":
        try:
            re.compile(params.get("regex") or "")
        except re.error:
            return _result(f, "Cannot verify", "Invalid or missing regex", t, params)
        if not params.get("regex"):
            return _result(f, "Cannot verify", "Invalid or missing regex", t, params)
    if t == "invalid_value" and not isinstance(params.get("allowed"), list):
        return _result(f, "Cannot verify", "allowed list missing", t, params)
    if t == "cross_column":
        if params.get("other") not in df.columns or params.get("op") not in OPS:
            return _result(f, "Cannot verify", "other column/operator missing or invalid", t, params)
        params.setdefault("kind", "numeric")

    rule = RULES.get(canon_of.get(col), {})
    try:
        mask = compute_mask(df, col, t, rule, params)
    except Exception as e:  # noqa: BLE001
        return _result(f, "Cannot verify", f"{type(e).__name__}: {e}", t, params)

    affected = int(mask.sum())
    idx = df.index[mask.values][:10]
    rows = [int(i) + 2 for i in idx]
    samples = [jsonable(v) for v in df.loc[idx, col].tolist()] if (col in df.columns and t != "duplicate_rows") else []

    # banking business rules for the mapped field
    biz = {}
    if rule:
        for bt in ("invalid_type", "out_of_range", "invalid_format", "invalid_value", "future_date"):
            if bt == "invalid_type" and rule["kind"] not in ("numeric", "date"):
                continue
            try:
                c = int(compute_mask(df, col, bt, rule, {}).sum())
                if c:
                    biz[bt] = c
            except Exception:  # noqa: BLE001
                pass

    dup = next((i["id"] for i in existing_issues
                if i["column"] == col and i["issue_type"] == t
                and (i.get("params") or {}).get("other") == params.get("other")), None)
    status = "Confirmed" if affected > 0 else "Needs review"
    note = (f"Verified on all rows: {affected} affected" if affected else
            "Check ran on all rows but no rows matched; finding is not supported by the data")
    return _result(f, status, note, t, params, affected, rows, samples,
                   {"business_rule_violations": biz, "duplicate_of": dup, "canonical": canon_of.get(col)})


def verify_all(df, findings: list, col_of: dict, existing_issues: list) -> list:
    return [verify_finding(df, f, col_of, existing_issues) for f in findings]
