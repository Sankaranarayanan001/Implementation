"""Library-backed cleaning tools (phonenumbers, email-validator, dateparser, price-parser, nameparser, rapidfuzz)."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process

from app.services.common.banking_rules import norm_name
from app.services.common.checks import _txt, blank_mask, to_date, to_num

# synonyms the libraries cannot know: lower-case key -> lower-case target



# ---------- phone (phonenumbers) ----------
PHONE_SENTINELS = {"0000000000", "1234567890", "9999999999", "1111111111", "12345"}


def fix_phone(v, region: str = "IN"):
    import phonenumbers
    t = _txt(v)
    if t is None:
        return np.nan
    try:
        p = phonenumbers.parse(t.strip(), region)
    except phonenumbers.NumberParseException:
        return np.nan
    num = str(p.national_number)
    if num in PHONE_SENTINELS or not phonenumbers.is_valid_number(p):
        return np.nan
    return num

def fix_customer_id(v):
    t = _txt(v)
    if t is None:
        return np.nan
    t = re.sub(r"\s+", "", t).upper()
    m = re.fullmatch(r"C(?:UST|US)-?(\d{1,4})", t)
    if not m:
        return np.nan
    out = f"CUST-{int(m.group(1)):04d}"
    return np.nan if out == "CUST-0000" else out


# ---------- email (email-validator) ----------
def fix_email(v):
    from email_validator import EmailNotValidError, validate_email
    t = _txt(v)
    if t is None:
        return np.nan
    t = re.sub(r"\s+", "", t).lower()
    try:
        return validate_email(t, check_deliverability=False).normalized
    except EmailNotValidError:
        return np.nan


# ---------- names (nameparser) ----------
def fix_name(v):
    from nameparser import HumanName
    t = _txt(v)
    if t is None:
        return v
    n = HumanName(" ".join(t.split()))
    n.capitalize(force=True)
    out = str(n).strip()
    return out or t


# ---------- dates (dateparser) ----------
def _dp(v):
    import dateparser
    t = _txt(v)
    if t is None:
        return pd.NaT
    d = dateparser.parse(t, settings={"DATE_ORDER": "DMY"})
    return pd.Timestamp(d) if d else pd.NaT


def parse_dates_lib(s: pd.Series) -> pd.Series:
    base = to_date(s)
    bad = ~blank_mask(s) & base.isna()
    if bad.any():
        base = base.copy()
        base[bad] = pd.to_datetime(s[bad].map(_dp), errors="coerce")
    return base


# ---------- money (price-parser) ----------
def _money(v):
    from price_parser import Price
    t = _txt(v)
    if t is None:
        return np.nan
    a = Price.fromstring(t).amount_float
    return float(a) if a is not None else np.nan


def parse_money_lib(s: pd.Series) -> pd.Series:
    x = to_num(s)
    bad = ~blank_mask(s) & x.isna()
    if bad.any():
        x = x.copy()
        x[bad] = s[bad].map(_money).astype("float64")
    return x

# ---------- categories (synonym table + spelling + rapidfuzz) ----------
def _k(v) -> str:
    return " ".join(str(v).lower().split())


def _sq(v) -> str:
    t = re.sub(r"[^a-z0-9]", "", str(v).lower())
    return t[:-1] if len(t) > 4 and t.endswith("s") else t


# (column-name regex, {variant: standard}). A redirect is used only if the standard value exists in the column.
SYNONYM_RULES = [
    (r"gender|(^|_)sex($|_)", {"m": "male", "f": "female", "o": "other", "man": "male", "woman": "female","x": "other"}),
    (r"collateral|default|(^|_)is_|(^|_)has_|flag|verified|insured|kyc",
     {"y": "yes", "n": "no", "true": "yes", "false": "no", "1": "yes", "0": "no"}),
    (r"collateral", {"not provided": "no", "none": "no", "nil": "no"}),
    (r"marital", {"widow": "widowed", "unmarried": "single", "divorcee": "divorced"}),
    (r"education", {"pg": "master", "post graduate": "master", "postgraduate": "master", "ug": "bachelor",
                    "under graduate": "bachelor", "undergraduate": "bachelor", "hs": "high school",
                    "phd": "doctorate", "doctoral": "doctorate"}),
    (r"employment|occupation", {"jobless": "unemployed", "not employed": "unemployed",
                                "business owner": "business", "freelancer": "self-employed",
                                "salary": "salaried"}),
    (r"purpose", {"car": "vehicle", "auto": "vehicle", "bike": "vehicle", "health": "medical",
                  "home loan": "home", "house": "home", "housing": "home"}),
    (r"loan_?status|repay", {"paid": "repaid", "not paid": "default", "unpaid": "default",
                             "defaulted": "default"}),
    (r"(^|_)status($|_)", {"complete": "completed", "done": "completed", "success": "completed",
                           "successful": "completed", "cancelled": "canceled"}),
    (r"account_?type|acct_?type", {"chk": "checking", "chequing": "checking", "checking account": "checking",
                                   "sav": "savings account", "savings": "savings account",
                                   "savings a/c": "savings account", "current": "current account",
                                   "current a/c": "current account", "fd": "fixed deposit",
                                   "cc": "credit card"}),
    (r"city", {"bombay": "mumbai", "calcutta": "kolkata", "kolkatta": "kolkata", "bangalore": "bengaluru",
               "gauhati": "guwahati", "new delhi": "delhi", "madras": "chennai", "poona": "pune","uttar-pradesh": "uttar pradesh"}),
    (r"state", {"orissa": "odisha", "uttaranchal": "uttarakhand"}),
    (r"channel", {"mobileapp": "mobile app", "phone": "phone banking"}),
]


def category_map(s: pd.Series, colname=None, params: dict | None = None) -> dict:
    """raw spelling -> standard spelling, only for values that should change."""
    params = params or {}
    raw = s.map(_txt).map(lambda v: None if v is None else " ".join(v.split()))
    uniq = raw.dropna().value_counts()
    if uniq.empty or len(uniq) > 200:
        return {}
    n = int(uniq.sum())
    cname = norm_name(colname or "")
    syn = {}
    for pat, d in SYNONYM_RULES:
        if re.search(pat, cname):
            syn.update(d)
    syn_sq = {_sq(k): v for k, v in syn.items()}
    umap = {_k(k): str(v).strip() for k, v in (params.get("mapping") or {}).items()}
    present = {_k(r) for r in uniq.index}

    keyof, forced = {}, {}
    for r in uniq.index:
        k = _k(r)
        if k in umap:
            forced[r] = umap[k]
            keyof[r] = _k(umap[k])
            continue
        tgt = syn.get(k) or syn_sq.get(_sq(k))
        keyof[r] = tgt if (tgt and tgt in present) else k
    first = {}
    for r in uniq.index:
        first.setdefault(_sq(keyof[r]), keyof[r])
    for r in uniq.index:
        if r not in forced:
            keyof[r] = first[_sq(keyof[r])]
    counts = {}
    for r, c in uniq.items():
        counts[keyof[r]] = counts.get(keyof[r], 0) + int(c)
    thr = max(int(params.get("min_count", 2)), int(0.01 * n))
    canon = [k for k, c in counts.items() if c >= thr]
    sq_canon = {}
    for k in canon:
        sq_canon.setdefault(_sq(k), k)

    target = {}
    for k in counts:
        if k in canon:
            target[k] = k
            continue
        t = sq_canon.get(_sq(k))
        if not t and len(k) >= 4 and canon:
            m = process.extractOne(k, canon, scorer=fuzz.ratio, score_cutoff=float(params.get("threshold", 90)))
            t = m[0] if m else None
        target[k] = t or k

    disp = {}
    for r in uniq.index:  # sorted by count, so the most common spelling wins
        disp.setdefault(_k(r), r)

    out = {}
    for r in uniq.index:
        tk = target[keyof[r]]
        shown = forced.get(r) or disp.get(tk) or tk.title()
        if r != shown:
            out[r] = shown
    return out

def fix_formatted_id(v, prefix: str, width: int):
    """Rebuild an ID as PREFIX + zero-padded number. If it cannot be rebuilt, keep the original."""
    t = _txt(v)
    if t is None:
        return v
    s = t.strip()
    if s.lower() == "unknown":
        return v
    digits = re.sub(r"\D", "", s)
    if not digits or int(digits) == 0 or len(digits.lstrip("0") or "0") > width:
        return v
    return f"{prefix}{int(digits):0{width}d}"
