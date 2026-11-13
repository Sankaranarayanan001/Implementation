from __future__ import annotations

import datetime as dt
import math
from pathlib import Path

import numpy as np
import pandas as pd


def jsonable(o):
    if o is None or o is pd.NaT:
        return None
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [jsonable(v) for v in o]
    if isinstance(o, np.ndarray):
        return jsonable(o.tolist())
    if isinstance(o, (bool, np.bool_)):
        return bool(o)
    if isinstance(o, (int, np.integer)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        f = float(o)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(o, (pd.Timestamp, dt.datetime, dt.date)):
        return o.isoformat()
    if isinstance(o, Path):
        return str(o)
    return str(o)


def _kind(v) -> str:
    if isinstance(v, (dt.datetime, dt.date, pd.Timestamp)):
        return "date"
    if isinstance(v, (bool, np.bool_)):
        return "bool"
    if isinstance(v, (int, float, np.integer, np.floating)):
        return "number"
    return "text"


def _to_text(v):
    if v is None or v is pd.NaT:
        return np.nan
    try:
        if pd.isna(v):
            return np.nan
    except (TypeError, ValueError):
        pass
    if isinstance(v, (dt.datetime, pd.Timestamp)):
        if (v.hour, v.minute, v.second) == (0, 0, 0):
            return v.strftime("%Y-%m-%d")
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, (float, np.floating)) and float(v).is_integer():
        return str(int(v))
    return str(v)


def normalize_mixed_types(df: pd.DataFrame) -> pd.DataFrame:
    """Columns holding more than one Python type (e.g. datetime + str, int + str) become all text."""
    changed = []
    for c in df.columns:
        s = df[c]
        if not pd.api.types.is_object_dtype(s):
            continue
        nn = s.dropna()
        if nn.empty:
            continue
        kinds = sorted(set(nn.map(_kind)))
        if len(kinds) <= 1:
            continue
        df[c] = s.map(_to_text)
        changed.append({"column": c, "types_found": kinds})
    df.attrs["normalized"] = changed
    return df


def read_table(path: Path) -> pd.DataFrame:
    suffix = Path(path).suffix.lower()
    if suffix == ".csv":
        try:
            df = pd.read_csv(path)
        except UnicodeDecodeError:
            df = pd.read_csv(path, encoding="latin-1")
    elif suffix in (".xlsx", ".xlsm"):
        df = pd.read_excel(path, engine="openpyxl")
    elif suffix == ".xls":
        df = pd.read_excel(path, engine="xlrd")
    else:
        raise ValueError(f"Unsupported file type: {suffix}")
    df.columns = [str(c).strip() for c in df.columns]
    return normalize_mixed_types(df.reset_index(drop=True))


def records(df: pd.DataFrame) -> list:
    clean = df.astype(object).where(df.notna(), None)
    return jsonable(clean.to_dict(orient="records"))
