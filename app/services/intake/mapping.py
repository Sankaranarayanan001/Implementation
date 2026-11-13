"""Step 4 – banking column identification and mapping."""
from __future__ import annotations

import re

import pandas as pd
from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ColumnMappingHistory
from app.services.common.banking_rules import ALIASES, CANONICAL, DESCRIPTIONS, RULES, anchored, norm_name
from app.core.config import settings
from app.services.common.checks import _txt
from app.services.ai.llm import ask_json

PATTERN_FIELDS = ["email", "ifsc_code", "pan_number"]


def _history(db: Session, owner_id: int) -> dict:
    rows = db.scalars(select(ColumnMappingHistory).where(ColumnMappingHistory.owner_id == owner_id)
                      .order_by(ColumnMappingHistory.uses.asc())).all()
    return {r.column_key: r.canonical for r in rows}  # highest 'uses' wins (later overwrite)


def _pattern_match(s: pd.Series):
    vals = [t.strip() for t in (_txt(v) for v in s.dropna().head(200)) if t and t.strip()]
    if not vals:
        return None
    for canon in PATTERN_FIELDS:
        pat = re.compile(anchored(RULES[canon]["regex"]))
        if sum(1 for v in vals if pat.match(v)) / len(vals) >= 0.8:
            return canon
    return None


def suggest_mappings(db: Session, owner_id: int, df: pd.DataFrame) -> tuple[list, str | None]:
    hist = _history(db, owner_id)
    alias_names, alias_canon = [], []
    for canon, al in ALIASES.items():
        for a in al + [canon]:
            alias_names.append(norm_name(a))
            alias_canon.append(canon)

    out, unmatched = [], []

    def entry(col, canon, conf, source):
        return {"column": col, "suggested": canon, "confidence": conf, "source": source,
                "samples": [str(x) for x in df[col].dropna().astype(str).head(3).tolist()]}

    for col in df.columns:
        key = norm_name(col)
        if key in hist:
            out.append(entry(col, hist[key], 0.95, "history"))
        elif key in alias_names:
            out.append(entry(col, alias_canon[alias_names.index(key)], 0.9, "alias"))
        else:
            m = process.extractOne(key, alias_names, scorer=fuzz.ratio, score_cutoff=85)
            if m:
                out.append(entry(col, alias_canon[m[2]], round(m[1] / 100 * 0.85, 2), "fuzzy"))
                continue
            p = _pattern_match(df[col])
            if p:
                out.append(entry(col, p, 0.8, "value_pattern"))
            else:
                e = entry(col, None, 0.0, "none")
                out.append(e)
                unmatched.append(e)

    llm_error = None
    if unmatched and settings.llm_enabled and settings.enable_ai_mapping:
        data, llm_error = ask_json(
            "You map spreadsheet columns of a banking dataset to canonical banking fields. "
            "Use only the canonical field names given, or null when nothing fits. "
            'Return {"mappings":[{"column":"<exact column>","canonical":"<field or null>"}]}.',
            {"canonical_fields": DESCRIPTIONS,
             "columns": [{"column": e["column"], "samples": e["samples"]} for e in unmatched[:40]]},
        )
        by_col = {e["column"]: e for e in unmatched}
        for m in (data or {}).get("mappings", []) or []:
            e = by_col.get(m.get("column"))
            if e and m.get("canonical") in CANONICAL:
                e.update(suggested=m["canonical"], confidence=0.6, source="qwen")

    elif unmatched:
        llm_error = "AI mapping skipped (enable ENABLE_AI_MAPPING=true to use Qwen); confirm unmatched columns manually."

    # one canonical field -> one column (keep most confident)
    best = {}
    for e in out:
        if e["suggested"] and (e["suggested"] not in best or e["confidence"] > best[e["suggested"]]["confidence"]):
            best[e["suggested"]] = e
    for e in out:
        if e["suggested"] and best[e["suggested"]] is not e:
            e.update(suggested=None, confidence=0.0, source="conflict")
    return out, llm_error


def validate_confirmation(df: pd.DataFrame, mappings: dict) -> dict:
    """Returns {column: canonical} with nulls dropped; raises ValueError on invalid input."""
    seen, clean = set(), {}
    for col, canon in mappings.items():
        if col not in df.columns:
            raise ValueError(f"Unknown column: {col}")
        if canon is None:
            continue
        if canon not in CANONICAL:
            raise ValueError(f"Unknown banking field: {canon}")
        if canon in seen:
            raise ValueError(f"Banking field mapped twice: {canon}")
        seen.add(canon)
        clean[col] = canon
    return clean


def remember_mappings(db: Session, owner_id: int, mappings: dict) -> None:
    for col, canon in mappings.items():
        key = norm_name(col)
        row = db.scalar(select(ColumnMappingHistory).where(
            ColumnMappingHistory.owner_id == owner_id, ColumnMappingHistory.column_key == key,
            ColumnMappingHistory.canonical == canon))
        if row:
            row.uses += 1
        else:
            db.add(ColumnMappingHistory(owner_id=owner_id, column_key=key, canonical=canon))
    db.commit()
