"""Step 14 – Python + Pandas cleaning engine (executes approved actions only)."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from app.services.common.banking_rules import RULES, id_format_for, is_date_name
from app.services.common.checks import _txt, blank_mask, case_map, col_kind, compute_mask, outlier_bounds, to_num
from app.services.actions.tools import (category_map, fix_email, fix_formatted_id, fix_name, fix_phone,
                                parse_dates_lib, parse_money_lib)

ACTION_ORDER = ["strip_whitespace", "placeholder_to_null", "sentinel_to_null", "unify_case",
                "merge_categories", "fix_names", "coerce_type","parse_dates", "parse_money", "fix_format_or_null",
                "map_to_allowed_or_null", "set_null", "clip_range", "cap_outliers", "fill_unknown",
                "fill_missing", "drop_rows", "drop_duplicates_on_column", "drop_duplicate_rows", "flag_only"]


def _rule(rec):
    return RULES.get(rec.get("canonical"), {})


def _mask(df, rec, t=None):
    return compute_mask(df, rec.get("column"), t or rec["issue_type"], _rule(rec), rec.get("issue_params") or {})


def a_flag(df, rec):
    return df, 0, "no change"


def a_strip(df, rec):
    col, n = rec["column"], int(_mask(df, rec, "whitespace").sum())
    df[col] = df[col].map(lambda v: " ".join(v.split()) if isinstance(v, str) else v)
    return df, n, ""


def a_placeholder(df, rec):
    m = _mask(df, rec, "placeholder")
    df.loc[m, rec["column"]] = np.nan
    return df, int(m.sum()), ""

def a_sentinel(df, rec):
    m = _mask(df, rec, "sentinel")
    df.loc[m, rec["column"]] = np.nan
    return df, int(m.sum()), "dummy values set empty"


def a_unify_case(df, rec):
    col = rec["column"]
    cm = case_map(df[col])
    n = int(_mask(df, rec, "case_inconsistency").sum())

    def fix(v):
        t = _txt(v)
        if t is None:
            return v
        raw = " ".join(t.split())
        return cm.get(raw.lower(), raw)

    df[col] = df[col].map(fix)
    return df, n, ""


def a_merge_categories(df, rec):
    col = rec["column"]
    cm = category_map(df[col], col, rec.get("params"))
    if not cm:
        return df, 0, "no variants found"
    n = int(compute_mask(df, col, "category_variant", {}, rec.get("params") or {}).sum())
    df[col] = df[col].map(lambda v: cm.get(" ".join(_txt(v).split()), v) if _txt(v) is not None else v)
    return df, n, f"merged {len(cm)} variant(s)"


def a_fix_names(df, rec):
    col = rec["column"]
    m = _mask(df, rec, "name_format")
    idx = df.index[m.values]
    df[col] = df[col].astype(object)  
    df.loc[idx, col] = [fix_name(v) for v in df.loc[idx, col]]
    return df, int(len(idx)), "reordered / capitalised"


def a_coerce(df, rec):
    col = rec["column"]
    kind = _rule(rec).get("kind") or (rec.get("issue_params") or {}).get("kind") or col_kind(df, col)
    n = int(compute_mask(df, col, "invalid_type", _rule(rec), {"kind": kind}).sum())
    if kind == "numeric":
        df[col] = parse_money_lib(df[col])
    elif kind == "date":
        df[col] = parse_dates_lib(df[col])
    else:
        return df, 0, "coerce_type not applicable to text columns"
    return df, n, f"converted to {kind}; unparseable values set empty"

def a_parse_dates(df, rec):
    col = rec["column"]
    n = int(compute_mask(df, col, "date_format").sum())
    df[col] = pd.to_datetime(parse_dates_lib(df[col]), errors="coerce").dt.normalize()
    return df, n, "converted to real dates; unreadable values set empty"

def a_parse_money(df, rec):
    col = rec["column"]
    n = int(compute_mask(df, col, "numeric_text").sum())
    df[col] = parse_money_lib(df[col])
    return df, n, "converted to numeric"


def a_set_null(df, rec):
    m = _mask(df, rec)
    df.loc[m, rec["column"]] = np.nan
    return df, int(m.sum()), ""


def a_clip(df, rec):
    col, p = rec["column"], {**(rec.get("issue_params") or {}), **(rec.get("params") or {})}
    mn, mx = p.get("min", _rule(rec).get("min")), p.get("max", _rule(rec).get("max"))
    n = int(compute_mask(df, col, "out_of_range", _rule(rec), {"min": mn, "max": mx}).sum())
    df[col] = to_num(df[col]).clip(lower=mn, upper=mx)
    return df, n, ""


def a_cap_outliers(df, rec):
    col = rec["column"]
    x = to_num(df[col])
    b = outlier_bounds(x, float((rec.get("params") or {}).get("k", 3.0)))
    if not b:
        return df, 0, "not enough data to compute bounds"
    n = int(((x < b[0]) | (x > b[1])).sum())
    df[col] = x.clip(lower=b[0], upper=b[1])
    return df, n, f"capped to [{b[0]:.2f}, {b[1]:.2f}]"


def a_fix_format(df, rec):
    col, rule, canon = rec["column"], _rule(rec), rec.get("canonical")
    p = rec.get("issue_params") or {}
    m = _mask(df, rec, "invalid_format")
    idx = df.index[m.values]
    if len(idx) == 0:
        return df, 0, "nothing to fix"
    if canon == "phone":
        fixer = fix_phone
    elif canon == "email":
        fixer = fix_email
    elif id_format_for(col, canon):
        _p, _w = id_format_for(col, canon)
        fixer = lambda v: fix_formatted_id(v, _p, _w)
    else:
        rx = p.get("regex") or rule.get("regex")
        if not rx:
            return df, 0, "no regex available"

        def fixer(v):
            t = _txt(v)
            if t is None:
                return v
            t = t.strip()
            if rule.get("upper"):
                t = t.upper()
            return t if re.fullmatch(rx, t) else np.nan

    df[col] = df[col].astype(object)
    df.loc[idx, col] = [fixer(v) for v in df.loc[idx, col]]
    return df, int(len(idx)), "fixed with library validator, otherwise set empty"


def a_map_allowed(df, rec):
    col = rec["column"]
    allowed = (rec.get("issue_params") or {}).get("allowed") or _rule(rec).get("allowed") or []
    amap = {str(a).strip().lower(): a for a in allowed}
    m = _mask(df, rec, "invalid_value")
    idx = df.index[m.values]
    df[col] = df[col].astype(object)
    df.loc[idx, col] = [amap.get((_txt(v) or "").strip().lower(), np.nan) for v in df.loc[idx, col]]
    return df, int(len(idx)), ""


def a_fill_unknown(df, rec):
    col = rec["column"]
    m = compute_mask(df, col, "missing")
    n = int(m.sum())
    if n == 0:
        return df, 0, "nothing to fill"
    df[col] = df[col].astype(object)
    df[col] = df[col].map(lambda v: "Unknown" if isinstance(v, str) and v.strip().lower() == "unknown" else v)
    df.loc[m, col] = "Unknown"
    return df, n, "filled with 'Unknown'"


def a_fill(df, rec):
    col, canon = rec["column"], rec.get("canonical")
    m = compute_mask(df, col, "missing")
    n = int(m.sum())
    if n == 0:
        return df, 0, "nothing to fill"
    kind = col_kind(df, col, canon)
    p = rec.get("params") or {}
    strat = p.get("strategy") or ("median" if kind == "numeric" else "mode")
    if strat in ("median", "mean") and kind == "numeric":
        x = to_num(df[col])
        val = x.median() if strat == "median" else x.mean()
        if pd.isna(val):
            return df, 0, "no numeric values to compute from"
        df[col] = x.where(~m, val)
        return df, n, f"filled with {strat}={val:.4g}"
    if strat == "constant":
        val = p.get("value")
    else:
        vc = df.loc[~m, col].value_counts()
        if vc.empty:
            return df, 0, "no values to compute mode"
        val = vc.index[0]
    df[col] = df[col].astype(object)
    df.loc[m, col] = val
    return df, n, f"filled with {strat}={val!r}"


def a_drop_rows(df, rec):
    m = _mask(df, rec)
    return df.loc[~m].copy(), int(m.sum()), "rows removed"


def a_drop_dup_col(df, rec):
    m = _mask(df, rec, "duplicate_values")
    return df.loc[~m].copy(), int(m.sum()), "rows removed (first occurrence kept)"


def a_drop_dup_rows(df, rec):
    before = len(df)
    out = df.drop_duplicates(keep="first").copy()
    return out, before - len(out), "rows removed (first occurrence kept)"


ACTIONS = {
    "flag_only": a_flag, "strip_whitespace": a_strip, "placeholder_to_null": a_placeholder,
    "unify_case": a_unify_case, "merge_categories": a_merge_categories, "fix_names": a_fix_names,
    "coerce_type": a_coerce, "parse_money": a_parse_money, "set_null": a_set_null, "clip_range": a_clip,
    "cap_outliers": a_cap_outliers, "fix_format_or_null": a_fix_format, "map_to_allowed_or_null": a_map_allowed,
    "fill_unknown": a_fill_unknown, "fill_missing": a_fill, "drop_rows": a_drop_rows,
    "drop_duplicates_on_column": a_drop_dup_col, "drop_duplicate_rows": a_drop_dup_rows,
    "sentinel_to_null": a_sentinel,
    "parse_dates": a_parse_dates,
}

def standardize_formats(work: pd.DataFrame):
    """Fixed formats: IDs as PREFIX+digits, date columns as real dates (shown dd-mm-yyyy in Excel)."""
    log = []
    for c in list(work.columns):
        spec = id_format_for(c)
        if spec:
            prefix, width = spec
            before = work[c].map(_txt)
            work[c] = work[c].astype(object).map(lambda v: fix_formatted_id(v, prefix, width))
            after = work[c].map(_txt)
            changed = int((~blank_mask(before) & (before != after)).sum())
            note = f"IDs set to {prefix} + {width} digits"
        elif is_date_name(c):
            nb = ~blank_mask(work[c])
            if not nb.any():
                continue
            parsed = pd.to_datetime(parse_dates_lib(work[c]), errors="coerce")
            if parsed[nb].notna().mean() < 0.5:
                continue  # not really a date column
            changed = 0 if pd.api.types.is_datetime64_any_dtype(work[c]) else int(nb.sum())
            work[c] = parsed.dt.normalize()
            note = "converted to real dates, shown as dd-mm-yyyy"
        else:
            continue
        log.append({"rec_id": f"AUTO-{c}", "column": c, "issue_type": "format_standardized",
                    "action": "standardize_format", "status": "applied", "affected_rows": changed,
                    "note": note, "rows_before": len(work), "rows_after": len(work)})
    return work, log


def execute(df: pd.DataFrame, approved: list):
    work, log = standardize_formats(df.copy())
    order = {a: i for i, a in enumerate(ACTION_ORDER)}
    for rec in sorted(approved, key=lambda r: (order.get(r["action"], 99), r["rec_id"])):
        before_rows = len(work)
        try:
            work, affected, note = ACTIONS[rec["action"]](work, rec)
            status = "applied" if rec["action"] != "flag_only" else "skipped"
            log.append({"rec_id": rec["rec_id"], "column": rec.get("column"), "issue_type": rec["issue_type"],
                        "action": rec["action"], "status": status, "affected_rows": int(affected), "note": note,
                        "rows_before": before_rows, "rows_after": len(work)})
        except Exception as e:  # noqa: BLE001
            log.append({"rec_id": rec["rec_id"], "column": rec.get("column"), "issue_type": rec["issue_type"],
                        "action": rec["action"], "status": "failed", "affected_rows": 0,
                        "note": f"{type(e).__name__}: {e}", "rows_before": before_rows, "rows_after": len(work)})
    for c in work.columns:
        if pd.api.types.is_object_dtype(work[c]) or pd.api.types.is_string_dtype(work[c]):
            work[c] = work[c].map(
                lambda v: "Unknown" if isinstance(v, str) and v.strip().lower() == "unknown" else v)
    cat_cols = {r["column"] for r in approved
                if r.get("canonical") in ("gender", "account_status", "kyc_status")
                and r.get("column") in work.columns}
    for c in cat_cols:
        work[c] = work[c].map(lambda v: v.title() if isinstance(v, str) and v.islower() else v)
    return work.reset_index(drop=True), log