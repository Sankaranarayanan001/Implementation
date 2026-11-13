"""Step 16 + learning lookups – Banking learning history."""
from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import LearningHistory
from app.services.common.banking_rules import norm_name


def rec_key(canonical, column, issue_type) -> str:
    return f"{canonical or norm_name(column or 'dataset')}|{issue_type}"


def history_hints(db: Session, owner_id: int, category: str) -> dict:
    rows = db.scalars(select(LearningHistory).where(
        LearningHistory.owner_id == owner_id, LearningHistory.category == category)
        .order_by(LearningHistory.id.desc()).limit(200)).all()
    approved, rejected, last_params = {}, {}, {}
    for r in rows:
        for d in (r.payload or {}).get("decisions", []):
            k = d.get("key")
            if not k:
                continue
            if d.get("decision") in ("approve", "modify"):
                approved.setdefault(k, Counter())[d.get("final_action")] += 1
                if d.get("params"):
                    last_params.setdefault(k, d["params"])
            else:
                rejected.setdefault(k, Counter())[d.get("recommended_action")] += 1
    hints = {}
    for k in set(approved) | set(rejected):
        a, rj = approved.get(k, Counter()), rejected.get(k, Counter())
        hints[k] = {"preferred_action": a.most_common(1)[0][0] if a else None,
                    "approved": sum(a.values()), "rejected": sum(rj.values()),
                    "params": last_params.get(k)}
    return hints


def save_learning(db: Session, ds, payload: dict) -> int:
    row = LearningHistory(owner_id=ds.owner_id, dataset_id=ds.id, category=ds.category, payload=payload)
    db.add(row)
    db.commit()
    return row.id
