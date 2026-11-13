"""Single source of truth for row-level checks. Every mask: True = violation."""
from __future__ import annotations

import operator
import re

import numpy as np
import pandas as pd

from app.services.common.banking_rules import RULES, norm_name

PLACEHOLDERS = {"n/a", "na", "#n/a", "null", "none", "nil", "nan", "-", "--", "?",
                "not available", "missing", "undefined", "tbd"}
DEBIT_WORDS = {"debit", "dr", "withdrawal", "payment", "fee", "purchase"}
CREDIT_WORDS = {"credit", "cr", "deposit", "refund"}
SENTINEL_NUMBERS = {-1.0, -99.0, -999.0, -9999.0, 99.0, 999.0, 9999.0, 99999.0, 999999.0,
                    9999999.0, 99999999.0, 999999999.0, 9999999999.0}
SENTINEL_DATES = {"1900-01-01", "1899-12-30", "1970-01-01", "1800-01-01", "0001-01-01",
                  "2099-01-01", "2100-01-01", "2999-12-31", "9999-12-31"}
SENTINEL_TS = [pd.Timestamp(x) for x in ("1900-01-01", "1970-01-01", "2099-01-01", "2100-01-01")]
_DATE_HINT = re.compile(r"(date|_dt$|^dt_|dob|birth|time)")
OPS = {"<=": operator.le, "<": operator.lt, ">=": operator.ge, ">": operator.gt,
       "==": operator.eq, "!=": operator.ne}
SUPPORTED_ISSUE_TYPES = {"missing", "placeholder", "whitespace", "case_inconsistency", "duplicate_values",
                         "duplicate_rows", "invalid_type", "out_of_range", "invalid_format", "invalid_value",
                         "outlier", "future_date", "cross_column", "numeric_text", "name_format",
                         "category_variant", "sentinel","date_format"}
_NUM_STRIP = re.compile(r"[₹$€£,\s]")
_ID_LIKE = re.compile(r"(^|_)(id|no|number|num|code|pin|zip|phone|mobile|account|acct|ifsc|pan)($|_)")


def identifier_like(col) -> bool:
    return bool(_ID_LIKE.search(norm_name(col)))


# ---------- scalar helpers ----------
def _txt(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, (float, np.floating)) and float(v).is_integer():
        return str(int(v))
    return str(v)


def _is_blank(v) -> bool:
    t = _txt(v)
    return t is None or t.strip() == ""


def _num(v):
    if v is None or isinstance(v, bool):
        return np.nan
    if isinstance(v, (int, float, np.integer, np.floating)):
        return float(v)
    if isinstance(v, str):
        t = _NUM_STRIP.sub("", v)
        if re.fullmatch(r"\(.*\)", t):
            t = "-" + t[1:-1]
        try:
            f = float(t)
            return f if np.isfinite(f) else np.nan
        except ValueError:
            return np.nan
    return np.nan


def _normalize(x: str, norm) -> str:
    if norm == "phone":
        return re.sub(r"[\s\-()]", "", x)
    return x.strip()


# ---------- series helpers ----------
def as_text(s: pd.Series) -> pd.Series:
    return s.map(_txt)


def blank_mask(s: pd.Series) -> pd.Series:
    return s.map(_is_blank).astype(bool)


def to_num(s: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
        return s.astype("float64")
    return s.map(_num).astype("float64")


def to_date(s: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(s):
        return s
    return pd.to_datetime(as_text(s), errors="coerce", dayfirst=True, format="mixed")


def is_numeric_like(s: pd.Series) -> bool:
    vals = s[~blank_mask(s)]
    if len(vals) == 0:
        return False
    if len(vals) > 2000:
        vals = vals.sample(2000, random_state=0)
    return bool(to_num(vals).notna().mean() >= 0.9)


def col_kind(df: pd.DataFrame, col, canon=None) -> str:
    if canon and canon in RULES:
        return RULES[canon]["kind"]
    s = df[col]
    if pd.api.types.is_bool_dtype(s):
        return "category"
    if pd.api.types.is_numeric_dtype(s):
        return "numeric"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "date"
    if is_numeric_like(s):
        return "numeric"
    return "text"


def _raw_key(s: pd.Series):
    raw = as_text(s).map(lambda v: None if v is None else " ".join(v.split()))
    key = raw.map(lambda v: None if v is None else v.lower())
    return raw, key


def case_map(s: pd.Series) -> dict:
    """lower-case key -> most common spelling, only for keys with >1 spelling."""
    raw, key = _raw_key(s)
    d = pd.DataFrame({"raw": raw, "key": key}).dropna()
    if d.empty:
        return {}
    top = d.groupby("key")["raw"].agg(lambda x: x.value_counts().idxmax())
    nun = d.groupby("key")["raw"].nunique()
    return {k: top[k] for k in nun[nun > 1].index}


def range_mask(x: pd.Series, mn, mx) -> pd.Series:
    m = pd.Series(False, index=x.index)
    if mn is not None:
        m = m | (x < mn)
    if mx is not None:
        m = m | (x > mx)
    return m.fillna(False).astype(bool)


def outlier_bounds(x: pd.Series, k: float = 3.0):
    v = x.dropna()
    if len(v) < 8:
        return None
    q1, q3 = v.quantile(0.25), v.quantile(0.75)
    iqr = q3 - q1
    if iqr == 0:
        return None
    return float(q1 - k * iqr), float(q3 + k * iqr)


# ---------- main dispatcher ----------
def compute_mask(df: pd.DataFrame, column, issue_type: str, rule: dict | None = None,
                 params: dict | None = None) -> pd.Series:
    rule = rule or {}
    params = params or {}
    false = pd.Series(False, index=df.index)
    t = issue_type
    if t not in SUPPORTED_ISSUE_TYPES:
        raise ValueError(f"unsupported issue type: {t}")
    if t == "duplicate_rows":
        return df.duplicated(keep="first")
    if column not in df.columns:
        raise KeyError(f"column not found: {column}")
    s = df[column]
    blank = blank_mask(s)

    if t == "missing":
        return blank
    if t == "placeholder":
        return s.map(lambda v: (_txt(v) or "").strip().lower() in PLACEHOLDERS).astype(bool)
    if t == "whitespace":
        return s.map(lambda v: isinstance(v, str) and (v != v.strip() or "  " in v)).astype(bool)
    if t == "case_inconsistency":
        cm = case_map(s)
        if not cm:
            return false
        raw, key = _raw_key(s)
        return pd.Series([(k in cm and r != cm[k]) for r, k in zip(raw, key)], index=s.index)
    if t == "duplicate_values":
        unk = s.map(lambda v: (_txt(v) or "").strip().lower() == "unknown").astype(bool)
        return s.duplicated(keep="first") & ~blank & ~unk
    if t == "invalid_type":
        kind = params.get("kind") or rule.get("kind")
        if kind == "numeric":
            return ~blank & to_num(s).isna()
        if kind == "date":
            return ~blank & to_date(s).isna()
        return false
    if t == "out_of_range":
        mn = params.get("min", rule.get("min"))
        mx = params.get("max", rule.get("max"))
        return range_mask(to_num(s), mn, mx)
    if t == "invalid_format":
        rx = params.get("regex") or rule.get("regex")
        if not rx:
            return false
        pat = re.compile(rx)
        norm = params.get("norm") or rule.get("norm")
        sent = {str(x).strip().lower() for x in (rule.get("sentinels") or [])}

        def _bad(v):
            x = _txt(v)
            if x is None or x.strip() == "" or x.strip().lower() == "unknown":
                return False
            if x.strip().lower() in sent:
                return True
            return not pat.fullmatch(_normalize(x, norm))

        return s.map(_bad).astype(bool)

        return s.map(_bad).astype(bool)
    if t == "invalid_value":
        allowed = params.get("allowed") or rule.get("allowed") or []
        allowed = {str(a).strip().lower() for a in allowed}
        if not allowed:
            return false
        return s.map(lambda v: (lambda x: x is not None and x.strip() != "" and x.strip().lower() != "unknown"
                                and x.strip().lower() not in allowed)(_txt(v))).astype(bool)
    if t == "numeric_text":
        return s.map(lambda v: isinstance(v, str) and v.strip() != "").astype(bool)
    if t == "name_format":
        return s.map(lambda v: isinstance(v, str) and v.strip() != ""
                     and ("," in v or v.strip().islower() or v.strip().isupper())).astype(bool)
    if t == "category_variant":
        from app.services.actions.tools import category_map
        cm = category_map(s, column, params)
        if not cm:
            return false
        return as_text(s).map(lambda v: v is not None and " ".join(v.split()) in cm).astype(bool)
    if t == "sentinel":
        kind = params.get("kind") or rule.get("kind")
        if kind not in ("numeric", "date"):
            if pd.api.types.is_datetime64_any_dtype(s):
                kind = "date"
            elif pd.api.types.is_numeric_dtype(s) or is_numeric_like(s):
                kind = "numeric"
            elif _DATE_HINT.search(norm_name(column)):
                kind = "date"
            else:
                return false
        if kind == "date":
            txt = as_text(s).map(lambda v: None if v is None else v.strip()[:10])
            m = txt.isin(SENTINEL_DATES)
            m = m | to_date(s).dt.normalize().isin(SENTINEL_TS)
            return m.astype(bool) if int(m.sum()) >= 2 else false
        x = to_num(s)
        v = x.dropna()
        if len(v) < 20:
            return false
        cand = [c for c in SENTINEL_NUMBERS if int((v == c).sum()) >= 2]
        if not cand:
            return false
        others = v[~v.isin(SENTINEL_NUMBERS)]
        hit = []
        for c in cand:
            if len(others) == 0:
                hit.append(c)
            elif c > 0 and c > (others.max() * 1.05 if others.max() > 0 else others.max()):
                hit.append(c)
            elif c < 0 and c < others.min():
                hit.append(c)
        return x.isin(hit).astype(bool) if hit else false
    if t == "date_format":
        return s.map(lambda v: isinstance(v, str) and v.strip() != ""
                     and v.strip().lower() != "unknown").astype(bool)    
    if t == "outlier":
        x = to_num(s)
        if params.get("lo") is not None and params.get("hi") is not None:
            return ((x < params["lo"]) | (x > params["hi"])).fillna(False).astype(bool)
        b = outlier_bounds(x, float(params.get("k", 3.0)))
        if not b:
            return false
        return ((x < b[0]) | (x > b[1])).fillna(False).astype(bool)
    if t == "future_date":
        d = to_date(s)
        return (d > pd.Timestamp.now()).fillna(False).astype(bool)
    if t == "cross_column":
        other = params.get("other")
        if other not in df.columns:
            raise KeyError(f"column not found: {other}")
        if params.get("check") == "age_dob":
            age = to_num(s)
            yrs = (pd.Timestamp.now() - to_date(df[other])).dt.days / 365.25
            return (age.notna() & yrs.notna() & ((age - yrs).abs() > 1.5))
        chk = params.get("check")
        if chk == "annual_monthly":
            a, b = to_num(s), to_num(df[other])
            return (a.notna() & b.notna() & (a > 0) & (((a - b * 12).abs() / a) > 0.05)).astype(bool)
        if chk == "amount_sign":
            amt = to_num(s)
            t = as_text(df[other]).map(lambda v: None if v is None else v.strip().lower())
            deb, cr = t.isin(DEBIT_WORDS), t.isin(CREDIT_WORDS)
            if deb.any() and (amt[deb] < 0).mean() > 0.5:
                m = (deb & (amt > 0)) | (cr & (amt < 0))
            else:
                m = (deb | cr) & (amt < 0)
            return m.fillna(False).astype(bool)        
        op = params.get("op")
        if op not in OPS:
            raise ValueError("invalid operator")
        if params.get("kind") == "date":
            x, y = to_date(s), to_date(df[other])
        else:
            x, y = to_num(s), to_num(df[other])
        return (x.notna() & y.notna() & ~OPS[op](x, y)).astype(bool)
    raise ValueError(t)
