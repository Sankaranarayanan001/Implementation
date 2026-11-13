"""Workflow orchestration for the 17-step banking cleaning pipeline."""
from __future__ import annotations

import datetime as dt
import logging
import shutil
import time
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.services.reporting import quality
from app.core.config import settings
from app.db.models import Dataset, User
from app.services.reporting import (
    report,
)
from app.services.actions import cleaning
from app.services.ai import ai_context, ai_discovery, history, recommendation
from app.services.analysis import profiling, results, validation, verification
from app.services.common.io_utils import jsonable, read_table
from app.services.intake import inspection, mapping
from app.services.reporting import postcheck

_log = logging.getLogger('uvicorn.error')


def _tick(label, t0):
    now = time.time()
    _log.info('analyze | %-28s %.1fs', label, now - t0)
    return now


STATUS_ORDER = ["uploaded", "mapped", "analyzed", "recommended", "reviewed", "cleaned"]
CATEGORIES = ["retail_banking", "transactions", "loans", "accounts", "cards", "customers", "other"]
PURPOSES = ["analytics", "ml_training", "reporting", "regulatory_compliance", "migration", "other"]
ALLOWED_EXT = {".csv", ".xlsx", ".xlsm", ".xls"}


def require(ds: Dataset, min_status: str) -> None:
    if STATUS_ORDER.index(ds.status) < STATUS_ORDER.index(min_status):
        raise HTTPException(409, f"Dataset is '{ds.status}'; complete the '{min_status}' step first.")


def ds_dir(ds_id: int) -> Path:
    p = settings.storage_dir / str(ds_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def load_df(ds: Dataset):
    return read_table(Path(ds.stored_path))


def set_state(db: Session, ds: Dataset, status: str | None = None, drop: tuple = (), **kw) -> None:
    st = {k: v for k, v in (ds.state or {}).items() if k not in drop}
    st.update(jsonable(kw))
    ds.state = st
    if status:
        ds.status = status
    ds.updated_at = dt.datetime.now(dt.timezone.utc)
    db.add(ds)
    db.commit()


def _col_of(mappings: dict) -> dict:
    return {canon: col for col, canon in mappings.items()}


# ---- Steps 2-4 ----
def upload(db: Session, user: User, filename: str, content: bytes, category: str, purpose: str) -> Dataset:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"Unsupported file type '{ext}'. Use CSV or Excel.")
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"File larger than {settings.max_upload_mb} MB")
    if category not in CATEGORIES:
        raise HTTPException(422, f"category must be one of {CATEGORIES}")
    if purpose not in PURPOSES:
        raise HTTPException(422, f"purpose must be one of {PURPOSES}")

    upload_started = time.perf_counter()
    ds = Dataset(owner_id=user.id, filename=Path(filename).name, stored_path="", category=category,
                 purpose=purpose, status="uploaded", state={})
    db.add(ds)
    db.commit()
    path = ds_dir(ds.id) / f"original{ext}"
    path.write_bytes(content)
    ds.stored_path = str(path)
    try:
        stage = time.perf_counter()
        df = read_table(path)
        _log.info("upload | read file %.2fs", time.perf_counter() - stage)
        if df.empty or df.shape[1] == 0:
            raise ValueError("File has no data")
    except Exception as e:  # noqa: BLE001
        shutil.rmtree(ds_dir(ds.id), ignore_errors=True)
        db.delete(ds)
        db.commit()
        raise HTTPException(400, f"Could not read file: {e}")
    stage = time.perf_counter()
    insp = inspection.inspect_dataframe(df)
    _log.info("upload | inspection %.2fs", time.perf_counter() - stage)
    stage = time.perf_counter()
    suggestions, llm_err = mapping.suggest_mappings(db, user.id, df)
    _log.info("upload | mapping suggestions %.2fs", time.perf_counter() - stage)
    set_state(db, ds, inspection=insp, suggested_mappings=suggestions, mapping_llm_error=llm_err)
    _log.info("upload | total %.2fs", time.perf_counter() - upload_started)
    return ds


def confirm_mappings(db: Session, ds: Dataset, user: User, mappings: dict) -> dict:
    require(ds, "uploaded")
    df = load_df(ds)
    try:
        clean = mapping.validate_confirmation(df, mappings)
    except ValueError as e:
        raise HTTPException(422, str(e))
    mapping.remember_mappings(db, user.id, clean)
    later = ("profile", "issues", "ai", "consolidated", "recommendations", "decisions", "cleaning_log",
             "post_validation", "cleaned_path", "report_path", "learning_id", "engine_notes")
    set_state(db, ds, status="mapped", drop=later, mappings=clean)
    return clean


# ---- Steps 5-11 ----
def analyze(db: Session, ds: Dataset, user: User) -> dict:
    require(ds, "mapped")
    st = ds.state
    df = load_df(ds)
    col_of = _col_of(st["mappings"])
    out = ds_dir(ds.id)

    t = time.time()
    profile = profiling.profile_dataframe(df, col_of, out)                       # 5
    t = _tick('5 profiling', t)
    val = validation.run_initial_validation(df, col_of)                          # 6, 7
    t = _tick('6-7 validation', t)
    issues = val["issues"]
    hints = history.history_hints(db, user.id, ds.category)
    ctx = ai_context.build_context(st["inspection"], col_of, profile, issues, hints)   # 8
    t = _tick('8 ai context', t)
    ai, llm_err = ai_discovery.interpret_and_discover(ctx, list(df.columns))     # 9
    t = _tick('9 qwen discovery', t)
    verified = verification.verify_all(df, ai["new_findings"], col_of, issues)   # 10
    t = _tick('10 verification', t)
    cons = results.consolidate(issues, verified, ai["interpretations"], llm_err, val["engine_notes"])  # 11
    set_state(db, ds, status="analyzed",
              drop=("recommendations", "decisions", "cleaning_log", "post_validation", "cleaned_path",
                    "report_path", "learning_id"),
              profile=profile, issues=issues, engine_notes=val["engine_notes"],
              ai={"findings": ai["new_findings"], "verified": verified, "llm_error": llm_err}, consolidated=cons)
    return cons


# ---- Step 12 ----
def recommend(db: Session, ds: Dataset, user: User) -> list:
    require(ds, "analyzed")
    df = load_df(ds)
    hints = history.history_hints(db, user.id, ds.category)
    recs, err = recommendation.build_recommendations(df, ds.state["consolidated"]["issues"], hints)
    set_state(db, ds, status="recommended", drop=("decisions", "cleaning_log", "post_validation", "cleaned_path",
                                                   "report_path", "learning_id"),
              recommendations=recs, recommendation_llm_error=err)
    return recs


# ---- Step 13 ----
def review(db: Session, ds: Dataset, decisions: list, approve_all_pending: bool):
    require(ds, "recommended")
    recs = {r["id"]: r for r in ds.state["recommendations"]}
    given = {}
    for d in decisions:
        if d.rec_id not in recs:
            raise HTTPException(422, f"Unknown recommendation: {d.rec_id}")
        if d.decision not in ("approve", "reject", "modify"):
            raise HTTPException(422, f"decision must be approve|reject|modify ({d.rec_id})")
        given[d.rec_id] = d
    final = []
    for rid, r in recs.items():
        d = given.get(rid)
        decision = d.decision if d else ("approve" if approve_all_pending else "reject")
        action, params = r["action"], r["params"]
        if decision == "modify":
            if not d.action or d.action not in r["allowed_actions"]:
                raise HTTPException(422, f"{rid}: action must be one of {r['allowed_actions']}")
            action, params = d.action, (d.params or {})
        final.append({
            "rec_id": rid, "decision": decision, "recommended_action": r["action"], "action": action,
            "params": params, "column": r["column"], "canonical": r["canonical"], "issue_type": r["issue_type"],
            "issue_params": r["issue_params"], "key": r["key"], "affected_rows": r["affected_rows"],
            "final_action": action if decision != "reject" else None,
        })

    drops = [f for f in final if f["decision"] != "reject"
             and f["action"] in ("drop_rows", "drop_duplicates_on_column", "drop_duplicate_rows")]
    est = sum(f["affected_rows"] for f in drops)
    total = ds.state["profile"]["rows"]
    pct = round(100 * est / max(total, 1), 2)
    warnings = []
    if pct > 5:
        warnings.append({
            "type": "data_loss",
            "message": f"Approved drop actions remove up to {est} of {total} rows ({pct}%). "
                       f"Overlapping rows are counted once at cleaning time, so the real number may be lower.",
            "rec_ids": [f["rec_id"] for f in drops],
        })
    set_state(db, ds, status="reviewed",
              drop=("cleaning_log", "post_validation", "cleaned_path", "report_path", "learning_id"),
              decisions=final, review_warnings=warnings)
    return final, warnings


# ---- Steps 14-17: Python cleaning, revalidation and reporting ----
def clean(db: Session, ds: Dataset, user: User) -> dict:
    require(ds, "reviewed")

    st = ds.state
    df = load_df(ds)
    col_of = _col_of(st["mappings"])

    approved = [d for d in st["decisions"] if d["decision"] in ("approve", "modify")]
    if not approved:
        raise HTTPException(422, "No approved cleaning actions.")

    out = ds_dir(ds.id)

    # Step 14: run the approved actions with the Python cleaning engine.
    stage = time.perf_counter()
    try:
        cleaned, exec_log = cleaning.execute(df, approved)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Cleaning failed: {type(exc).__name__}: {exc}")
    _log.info("clean | python cleaning %.2fs", time.perf_counter() - stage)

    # Step 15: re-run the Python validation checks on the cleaned data.
    stage = time.perf_counter()
    before_issues = st["consolidated"]["issues"]
    unmapped = {c for c in df.columns if not st["mappings"].get(c)}
    post = postcheck.post_validate(
        cleaned, col_of, before_issues, approved, len(df),
        unmapped_columns=unmapped,
    )
    _log.info("clean | post-validation %.2fs", time.perf_counter() - stage)

    # Merge the engine log with the revalidation result.
    constraint_map = {c["rec_id"]: c for c in post["approved_constraints"]}
    log = []
    for entry in exec_log:
        res = constraint_map.get(entry["rec_id"]) or {}
        remaining = res.get("remaining")
        status = entry["status"]
        note = entry.get("note", "")
        if status == "applied":
            if res.get("satisfied") is True:
                status = "verified"
                note = (note + "; " if note else "") + "resolved according to Python revalidation"
            elif remaining:
                status = "needs_review"
                note = (note + "; " if note else "") + f"{remaining} violating row(s) remain"
        log.append({**entry, "status": status, "note": note, "remaining_issues": remaining})
    log = quality.fix_log_status(log)
    post["comparison"] = quality.recount_outliers(cleaned, post.get("comparison", []), before_issues)
    qsum = quality.build_summary(before_issues, post, st["decisions"], len(df), len(cleaned),
                                 st["profile"]["column_count"])
    execution = {
        "engine": "python",
        "actions_total": len(exec_log),
        "actions_applied": sum(1 for e in exec_log if e["status"] == "applied"),
        "actions_skipped": sum(1 for e in exec_log if e["status"] == "skipped"),
        "actions_failed": sum(1 for e in exec_log if e["status"] == "failed"),
    }

    # Step 17: final Excel and HTML report.
    new_state = {**st, "cleaning_log": jsonable(log), "post_validation": post,
                 "execution": execution, "quality": qsum}
    cleaned_path = out / "cleaned.xlsx"
    report_path = out / "report.html"
    report.write_excel(cleaned_path, cleaned, new_state)
    report_path.write_text(report.build_html(ds, new_state), encoding="utf-8")

    # Step 16: save learning history.
    payload = jsonable({
        "mappings": st["mappings"],
        "dataset_profile": {
            "rows": st["profile"]["rows"],
            "columns": [
                {"name": c["name"], "kind": c["kind"], "missing_pct": c["missing_pct"], "unique": c["unique"]}
                for c in st["profile"]["columns"]
            ],
        },
        "detected_issues": [
            {k: i[k] for k in ("id", "column", "issue_type", "affected_rows", "severity")}
            for i in before_issues
        ],
        "validation_results": {
            "engine_notes": st.get("engine_notes"),
            "approved_constraints": post["approved_constraints"],
        },
        "decisions": st["decisions"],
        "cleaning_actions": log,
        "execution": execution,
        "before_after": {
            "rows_before": post["rows_before"],
            "rows_after": post["rows_after"],
            "comparison": post["comparison"],
        },
    })
    learn_id = history.save_learning(db, ds, payload)

    set_state(
        db, ds, status="cleaned",
        cleaning_log=log, post_validation=post, execution=execution,
        cleaned_path=str(cleaned_path), report_path=str(report_path), learning_id=learn_id,
    )
    dropped_pct = round(100 * (post["rows_before"] - post["rows_after"]) / max(post["rows_before"], 1), 2)
    set_state(db, ds, rows_dropped_pct=dropped_pct)
    return {"rows_before": post["rows_before"], "rows_after": post["rows_after"], "rows_dropped_pct": dropped_pct,
            "issues_before": post["issues_before"], "issues_after": post["issues_after"],
            "cleaning_log": log, "download": f"/datasets/{ds.id}/download", "report": f"/datasets/{ds.id}/report"}

# ---- Delete dataset files (database record is kept) ----
def delete_dataset(db: Session, ds: Dataset) -> None:
    shutil.rmtree(settings.storage_dir / str(ds.id), ignore_errors=True)
    set_state(db, ds, status="deleted", drop=("cleaned_path", "report_path"))