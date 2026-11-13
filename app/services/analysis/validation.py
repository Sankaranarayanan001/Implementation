"""Step 6 + 7 – Pandera, Great Expectations and custom Pandas validators; merge & de-duplicate."""
from __future__ import annotations
import re
import pandas as pd


from app.services.common.checks import (blank_mask, as_text, col_kind, compute_mask, identifier_like, outlier_bounds, to_num)
from app.services.common.banking_rules import CROSS_RULES, RULES, anchored, generic_range, is_date_name, norm_name
from app.services.common.io_utils import jsonable

DESC = {
    "missing": "missing / empty values",
    "placeholder": "placeholder values (N/A, null, -, ...) used instead of real data",
    "whitespace": "leading/trailing/double whitespace",
    "case_inconsistency": "same value spelled with inconsistent case",
    "duplicate_values": "duplicate values in a column that must be unique",
    "duplicate_rows": "fully duplicated rows",
    "invalid_type": "values that do not match the expected data type",
    "out_of_range": "values outside the allowed business range",
    "invalid_format": "values not matching the expected format",
    "invalid_value": "values not in the allowed list",
    "outlier": "extreme statistical outliers",
    "future_date": "dates in the future",
    "cross_column": "inconsistent with another column",
    "numeric_text": "numbers stored as text (currency symbols, commas)",
    "name_format": "names in 'Last, First' form or all upper/lower case",
    "category_variant": "same category written in different variants",
    "sentinel": "placeholder dummy values (e.g. 2099-01-01, 999, 999999999)",
    "date_format": "dates stored as text or in mixed formats",
}
ERROR_TYPES = {"invalid_type", "out_of_range", "invalid_format", "invalid_value", "future_date",
               "duplicate_values", "cross_column", "sentinel"}
WARN_TYPES = {"duplicate_rows", "outlier", "case_inconsistency", "placeholder",
              "numeric_text", "name_format", "category_variant","date_format"}
SEV_RANK = {"error": 0, "warning": 1, "info": 2}


def severity_of(t, canon, count, n) -> str:
    if t in ERROR_TYPES:
        return "error"
    if t == "missing":
        if RULES.get(canon, {}).get("required"):
            return "error"
        return "warning" if count / max(n, 1) > 0.05 else "info"
    if t in WARN_TYPES:
        return "warning"
    return "info"


def _sig(column, t, count, source, params=None):
    return {"column": column, "issue_type": t, "count": int(count), "source": source, "params": params or {}}


def _applicable_types(rule: dict) -> list:
    types = []
    kind = rule["kind"]
    if kind in ("numeric", "date"):
        types.append("invalid_type")
    if kind == "numeric" and (rule.get("min") is not None or rule.get("max") is not None):
        types.append("out_of_range")
    if rule.get("no_future"):
        types.append("future_date")
    if rule.get("regex"):
        types.append("invalid_format")
    if rule.get("allowed"):
        types.append("invalid_value")
    if rule.get("unique"):
        types.append("duplicate_values")
    
    return types


# ---------------- Pandera ----------------
def run_pandera(df, col_of):
    try:
        try:
            import pandera.pandas as pa
        except Exception:  # noqa: BLE001
            import pandera as pa
    except Exception as e:  # noqa: BLE001
        return [], f"pandera unavailable: {e}"

    def make_check(t, rule):
        def fn(s):
            d = pd.DataFrame({"x": s.reset_index(drop=True)})
            m = compute_mask(d, "x", t, rule, {})
            return pd.Series(~m.values, index=s.index)
        return pa.Check(fn, name=t, ignore_na=False)

    columns = {}
    for canon, col in col_of.items():
        rule = RULES.get(canon)
        if not rule or col not in df.columns:
            continue
        checks = [make_check(t, rule) for t in _applicable_types(rule)]
        columns[col] = pa.Column(checks=checks, nullable=not rule.get("required", False), required=True)
    if not columns:
        return [], None
    schema = pa.DataFrameSchema(columns, strict=False)
    signals = []
    try:
        schema.validate(df, lazy=True)
    except Exception as e:  # noqa: BLE001
        fc = getattr(e, "failure_cases", None)
        if fc is None:
            return [], f"pandera failed: {type(e).__name__}: {e}"
        names = set(DESC)
        for (col, chk), g in fc.groupby(["column", "check"], dropna=True):
            chk = str(chk)
            t = "missing" if chk == "not_nullable" else next((n for n in names if n in chk), None)
            if t and col in df.columns:
                signals.append(_sig(col, t, len(g), "pandera"))
    return signals, None


# ---------------- Great Expectations ----------------
def run_great_expectations(df, col_of):
    from app.core.config import settings
    if not settings.enable_great_expectations:
        return [], 'great_expectations disabled'
    try:
        import great_expectations as gx
        from great_expectations import expectations as gxe
    except Exception as e:  # noqa: BLE001
        return [], f"great_expectations unavailable: {e}"
    # text view for string checks, numeric view for ranges
    data = {}
    for canon, col in col_of.items():
        if canon in RULES and col in df.columns:
            data[col] = as_text(df[col]).astype(object)
            if RULES[canon]["kind"] == "numeric":
                data[f"{col}__num"] = to_num(df[col])
    if not data:
        return [], None
    gdf = pd.DataFrame(data)
    try:
        ctx = gx.get_context(mode="ephemeral")
        src = ctx.data_sources.add_pandas("banking_src")
        asset = src.add_dataframe_asset("banking_asset")
        bdef = asset.add_batch_definition_whole_dataframe("whole")
        batch = bdef.get_batch(batch_parameters={"dataframe": gdf})
    except Exception as e:  # noqa: BLE001
        return [], f"great_expectations setup failed: {type(e).__name__}: {e}"

    signals, errors = [], []

    def run(exp, col, t):
        try:
            res = batch.validate(exp)
            if not res.success:
                cnt = int((res.result or {}).get("unexpected_count") or 0)
                signals.append(_sig(col, t, cnt, "great_expectations"))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{col}/{t}: {type(e).__name__}")

    for canon, col in col_of.items():
        rule = RULES.get(canon)
        if not rule or col not in gdf.columns:
            continue
        if rule.get("required"):
            run(gxe.ExpectColumnValuesToNotBeNull(column=col), col, "missing")
        if rule.get("unique"):
            run(gxe.ExpectColumnValuesToBeUnique(column=col), col, "duplicate_values")
        if rule.get("regex") and not rule.get("norm"):
            run(gxe.ExpectColumnValuesToMatchRegex(column=col, regex=anchored(rule["regex"])), col, "invalid_format")
        if rule["kind"] == "numeric" and (rule.get("min") is not None or rule.get("max") is not None):
            run(gxe.ExpectColumnValuesToBeBetween(column=f"{col}__num", min_value=rule.get("min"),
                                                  max_value=rule.get("max")), col, "out_of_range")
    return signals, ("; ".join(errors[:5]) or None)


# ---------------- Custom pandas validators ----------------
_UNIQ_NAME = re.compile(r"(transaction|txn|loan|application|order|record|reference|ref|invoice)_?(id|no|number|num)$")
_ID_COL = re.compile(r"(^|_)id$")


def _expect_unique(df, col) -> bool:
    n = norm_name(col)
    nb = ~blank_mask(df[col])
    if nb.sum() < 20:
        return False
    if _UNIQ_NAME.search(n):
        return True
    if _ID_COL.search(n):
        return df[col][nb].nunique() / nb.sum() >= 0.9
    return False


def _find(df, pattern):
    for c in df.columns:
        if re.search(pattern, norm_name(c)):
            return c
    return None

def run_custom(df, col_of):
    canon_of = {v: k for k, v in col_of.items()}
    sig = []

    def add(col, t, mask, params=None):
        c = int(mask.sum())
        if c:
            sig.append(_sig(col, t, c, "custom_pandas", params))

    for col in df.columns:
        canon = canon_of.get(col)
        kind = col_kind(df, col, canon)
        add(col, "missing", compute_mask(df, col, "missing"))
        add(col, "placeholder", compute_mask(df, col, "placeholder"))
        try:
            add(col, "sentinel", compute_mask(df, col, "sentinel", RULES.get(canon, {}), {}))
        except Exception:  # noqa: BLE001
            pass
        rule = RULES.get(canon) or {}
        for t in (_applicable_types(rule) if rule else []):
            if t == "invalid_type" and kind == "date":
                continue
            try:
                add(col, t, compute_mask(df, col, t, rule, {}))
            except Exception:  # noqa: BLE001
                pass
        if kind == "date" or is_date_name(col):
            add(col, "date_format", compute_mask(df, col, "date_format"))
        if kind == "numeric" and (canon not in RULES):
            gr = generic_range(col)
            if gr:
                p = {k: v for k, v in gr.items() if v is not None}
                add(col, "out_of_range", compute_mask(df, col, "out_of_range", {}, p), p)
        if not RULES.get(canon, {}).get("unique") and _expect_unique(df, col):
            add(col, "duplicate_values", compute_mask(df, col, "duplicate_values"))        
        s = df[col]
        if pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s):
            add(col, "whitespace", compute_mask(df, col, "whitespace"))
            nb = int((~blank_mask(s)).sum())
            nu = int(s.nunique())
            if kind in ("text", "category") and nb > 0 and nu <= 50 and nu / nb <= 0.5:
                add(col, "case_inconsistency", compute_mask(df, col, "case_inconsistency"))
                add(col, "category_variant", compute_mask(df, col, "category_variant"))
        if kind == "numeric" and not identifier_like(col):
            b = outlier_bounds(to_num(df[col]))
            if b:
                p = {"lo": b[0], "hi": b[1]}
                add(col, "outlier", compute_mask(df, col, "outlier", {}, p), p)
        if kind == "numeric" and (pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s)):
            add(col, "numeric_text", compute_mask(df, col, "numeric_text"))
        if canon == "customer_name":
            add(col, "name_format", compute_mask(df, col, "name_format"))
    add(None, "duplicate_rows", compute_mask(df, None, "duplicate_rows"))

    for a, b, op in CROSS_RULES:
        if a in col_of and b in col_of:
            p = {"other": col_of[b], "op": op, "kind": "date"}
            add(col_of[a], "cross_column", compute_mask(df, col_of[a], "cross_column", {}, p), p)
    if "age" in col_of and "date_of_birth" in col_of:
        p = {"check": "age_dob", "other": col_of["date_of_birth"]}
        add(col_of["age"], "cross_column", compute_mask(df, col_of["age"], "cross_column", {}, p), p)
    amt = col_of.get("transaction_amount") or _find(df, r"^(txn_|transaction_)?amount$")
    typ = col_of.get("transaction_type") or _find(df, r"^(txn_|transaction_)?type$")
    if amt and typ and amt != typ:
        p = {"check": "amount_sign", "other": typ}
        add(amt, "cross_column", compute_mask(df, amt, "cross_column", {}, p), p)
    ann = _find(df, r"^(annual|yearly)_(income|salary)$")
    mon = _find(df, r"^monthly_(income|salary)$")
    if ann and mon:
        p = {"check": "annual_monthly", "other": mon}
        add(ann, "cross_column", compute_mask(df, ann, "cross_column", {}, p), p)    
    return sig


# ---------------- Merge (Step 7) ----------------
def merge_signals(df, signals, col_of):
    canon_of = {v: k for k, v in col_of.items()}
    groups = {}
    for sg in signals:
        key = (sg["column"], sg["issue_type"], (sg.get("params") or {}).get("other"))
        g = groups.setdefault(key, {"sources": set(), "count": 0, "params": sg.get("params") or {}})
        g["sources"].add(sg["source"])
        g["count"] = max(g["count"], sg["count"])
        if sg.get("params"):
            g["params"] = sg["params"]

    n = len(df)
    issues = []
    for (col, t, _other), g in groups.items():
        canon = canon_of.get(col)
        rule = RULES.get(canon, {})
        count, rows, samples = g["count"], [], []
        try:
            mask = compute_mask(df, col, t, rule, g["params"])
            c = int(mask.sum())
            if c == 0:
                continue  # authoritative recompute says no violation
            count = c
            idx = df.index[mask.values][:10]
            rows = [int(i) + 2 for i in idx]  # Excel row number (header = row 1)
            if col in df.columns and t != "duplicate_rows":
                samples = [jsonable(v) for v in df.loc[idx, col].tolist()]
        except Exception:  # noqa: BLE001
            pass
        issues.append({
            "column": col, "canonical": canon, "issue_type": t,
            "severity": severity_of(t, canon, count, n),
            "description": f"{count} row(s): {DESC.get(t, t)}" + (f" in '{col}'" if col else ""),
            "affected_rows": count, "affected_pct": round(100 * count / max(n, 1), 2),
            "sample_rows": rows, "sample_values": samples,
            "sources": sorted(g["sources"]), "params": g["params"],
        })
    issues.sort(key=lambda i: (SEV_RANK[i["severity"]], -i["affected_rows"]))
    for k, i in enumerate(issues, 1):
        i["id"] = f"ISS-{k:03d}"
    return issues


def run_initial_validation(df, col_of) -> dict:
    from app.core.config import settings

    notes = {}
    if settings.fast_mode:
        # Custom Pandas checks are the primary deterministic engine in Fast Mode.
        # Pandera and Great Expectations remain available in Full Mode to avoid
        # repeating overlapping checks on every upload/clean operation.
        p_sig, g_sig = [], []
        notes["pandera"] = "skipped in FAST_MODE"
        notes["great_expectations"] = "skipped in FAST_MODE"
    else:
        p_sig, notes["pandera"] = run_pandera(df, col_of)
        g_sig, notes["great_expectations"] = run_great_expectations(df, col_of)
    c_sig = run_custom(df, col_of)
    issues = merge_signals(df, p_sig + g_sig + c_sig, col_of)
    return {"issues": jsonable(issues), "engine_notes": notes,
            "engine_counts": {"pandera": len(p_sig), "great_expectations": len(g_sig), "custom": len(c_sig)}}
