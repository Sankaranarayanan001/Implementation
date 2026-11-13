"""Step 5 – data profiling (Pandas + YData Profiling)."""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pandas as pd

from app.core.config import settings
from app.services.common.checks import (as_text, blank_mask, col_kind, compute_mask, identifier_like,
                                 to_date, to_num)
from app.services.common.io_utils import jsonable


def _pattern(t: str) -> str:
    return re.sub(r"[A-Za-z]", "A", re.sub(r"\d", "9", t))[:30]


def profile_column(df: pd.DataFrame, c: str, canon: str | None) -> dict:
    s = df[c]
    n = len(df)
    blank = blank_mask(s)
    nb = ~blank
    kind = col_kind(df, c, canon)
    info = {
        "name": c, "canonical": canon, "dtype": str(s.dtype), "kind": kind,
        "missing": int(blank.sum()),
        "missing_pct": round(float(blank.mean() * 100), 2) if n else 0.0,
        "unique": int(s[nb].nunique()),
        "duplicate_values": int((s.duplicated(keep="first") & nb).sum()),
    }
    texts = as_text(s[nb])
    info["top_values"] = {str(k): int(v) for k, v in texts.value_counts().head(5).items()}
    unusual = []

    ph = compute_mask(df, c, "placeholder")
    if ph.sum():
        unusual.append(f"{int(ph.sum())} placeholder value(s), e.g. {as_text(s[ph]).head(3).tolist()}")
    try:
        sm = compute_mask(df, c, "sentinel", {}, {})
        if sm.sum():
            unusual.append(f"{int(sm.sum())} sentinel value(s), e.g. {as_text(s[sm]).head(3).tolist()}")
    except Exception:  # noqa: BLE001
        pass

    if kind == "numeric":
        x = to_num(s)
        v = x.dropna()
        if len(v):
            info.update(min=float(v.min()), max=float(v.max()), mean=float(v.mean()),
                        median=float(v.median()), std=float(v.std()) if len(v) > 1 else 0.0,
                        zeros=int((v == 0).sum()), negatives=int((v < 0).sum()))
            if len(v) > 2:
                info["skew"] = float(v.skew())
        bad = nb & x.isna()
        if bad.sum():
            unusual.append(f"{int(bad.sum())} non-numeric value(s), e.g. {as_text(s[bad]).head(3).tolist()}")
        if not identifier_like(c):
            om = compute_mask(df, c, "outlier")
            if om.sum():
                unusual.append(f"{int(om.sum())} extreme value(s), e.g. {x[om].head(3).tolist()}")
    elif kind == "date":
        d = to_date(s)
        if d.notna().any():
            info["date_min"], info["date_max"] = str(d.min()), str(d.max())
        bad = nb & d.isna()
        info["unparsed"] = int(bad.sum())
        if bad.sum():
            unusual.append(f"{int(bad.sum())} unparseable date(s), e.g. {as_text(s[bad]).head(3).tolist()}")
    else:
        if len(texts):
            lens = texts.map(len)
            info.update(len_min=int(lens.min()), len_max=int(lens.max()), len_mean=round(float(lens.mean()), 2))
            pats = Counter(texts.head(settings.profile_sample_rows).map(_pattern))
            info["pattern_count"] = len(pats)
            info["top_patterns"] = {k: int(v) for k, v in pats.most_common(5)}
            vc = texts.value_counts()
            if 0 < len(vc) and len(vc) / max(len(texts), 1) < 0.05:
                rare = vc[vc == 1].index.tolist()[:5]
                if rare:
                    unusual.append(f"rare category value(s): {rare}")
    info["unusual"] = unusual
    return info


def profile_dataframe(df: pd.DataFrame, col_of: dict, out_dir: Path) -> dict:
    canon_of = {v: k for k, v in col_of.items()}
    cols = [profile_column(df, c, canon_of.get(c)) for c in df.columns]

    corr = []
    num = [c["name"] for c in cols if c["kind"] == "numeric" and not identifier_like(c["name"])]
    if len(num) >= 2:
        m = pd.DataFrame({c: to_num(df[c]) for c in num}).corr()
        for i, a in enumerate(num):
            for b in num[i + 1:]:
                r = m.loc[a, b]
                if pd.notna(r) and abs(r) >= 0.8:
                    corr.append({"a": a, "b": b, "pearson": round(float(r), 3)})

    report_file, ydata_note, alerts = None, None, []
    try:
        if not settings.enable_ydata:
            raise RuntimeError('disabled (set ENABLE_YDATA=true to generate the HTML profile)')
        from ydata_profiling import ProfileReport
        sample = df if len(df) <= settings.profile_sample_rows else df.sample(settings.profile_sample_rows, random_state=0)
        rep = ProfileReport(sample.copy(), minimal=True, title="Banking dataset profile", progress_bar=False)
        path = Path(out_dir) / "ydata_profile.html"
        rep.to_file(path)
        report_file = str(path)
        try:
            alerts = [str(a) for a in rep.get_description().alerts][:50]
        except Exception:  # noqa: BLE001
            pass
    except Exception as e:  # noqa: BLE001
        ydata_note = f"ydata-profiling skipped: {type(e).__name__}: {e}"

    return jsonable({
        "rows": len(df), "columns": cols, "column_count": len(cols),
        "duplicate_rows": int(df.duplicated().sum()),
        "total_missing_cells": int(sum(c["missing"] for c in cols)),
        "correlations": corr, "ydata_report": report_file, "ydata_alerts": alerts, "ydata_note": ydata_note,
    })
