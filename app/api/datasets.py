from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
import shutil
from app.db.models import LearningHistory
from app.core.security import get_current_user
from app.db.models import Dataset, User
from app.db.session import get_db
from app.schemas import MappingConfirmIn, ReviewIn
from app.services import pipeline
from app.services.common.banking_rules import CANONICAL, DESCRIPTIONS
from app.services.ai.recommendation import ALL_ACTIONS
from frontend.services.api import api_call

router = APIRouter(prefix="/datasets", tags=["2 · Banking cleaning workflow"])


def get_ds(db: Session, ds_id: int, user: User) -> Dataset:
    ds = db.get(Dataset, ds_id)
    if not ds or ds.owner_id != user.id or ds.status == "deleted":
        raise HTTPException(404, "Dataset not found")
    return ds

def delete_dataset(token, dataset_id):
    response = api_call(
        "DELETE",
        f"/datasets/{dataset_id}",
        token=token
    )

    return response.json()

@router.delete("/{ds_id}")
def delete_dataset(ds_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ds = get_ds(db, ds_id, user)
    pipeline.delete_dataset(db, ds)
    return {"dataset_id": ds_id, "message": "Dataset files deleted."}

@router.get("/options")
def options(user: User = Depends(get_current_user)):
    return {"categories": pipeline.CATEGORIES, "purposes": pipeline.PURPOSES,
            "banking_fields": DESCRIPTIONS, "cleaning_actions": ALL_ACTIONS}


@router.get("")
def list_datasets(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.scalars(select(Dataset).where(Dataset.owner_id == user.id, Dataset.status != "deleted").order_by(Dataset.id.desc())).all()
    return [{"id": d.id, "filename": d.filename, "category": d.category, "purpose": d.purpose,
             "status": d.status, "created_at": d.created_at} for d in rows]


# Steps 2-4
@router.post("/upload", status_code=201)
def upload(file: UploadFile = File(...), category: str = Form("retail_banking"), purpose: str = Form("analytics"),
           db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ds = pipeline.upload(db, user, file.filename or "upload", file.file.read(), category, purpose)
    st = ds.state
    return {"dataset_id": ds.id, "status": ds.status, "inspection": st["inspection"],
            "suggested_mappings": st["suggested_mappings"], "mapping_llm_error": st.get("mapping_llm_error"),
            "available_banking_fields": CANONICAL}


@router.post("/{ds_id}/mappings/confirm")
def confirm(ds_id: int, body: MappingConfirmIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ds = get_ds(db, ds_id, user)
    clean = pipeline.confirm_mappings(db, ds, user, body.mappings)
    return {"dataset_id": ds.id, "status": ds.status, "mappings": clean}


# Steps 5-11
@router.post("/{ds_id}/analyze")
def analyze(ds_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ds = get_ds(db, ds_id, user)
    cons = pipeline.analyze(db, ds, user)
    return {"dataset_id": ds.id, "status": ds.status, **cons}


# Step 12
@router.post("/{ds_id}/recommendations")
def recommendations(ds_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ds = get_ds(db, ds_id, user)
    recs = pipeline.recommend(db, ds, user)
    return {"dataset_id": ds.id, "status": ds.status, "recommendations": recs,
            "llm_error": ds.state.get("recommendation_llm_error")}


# Step 13
@router.post("/{ds_id}/review")
def review(ds_id: int, body: ReviewIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ds = get_ds(db, ds_id, user)
    final, warnings = pipeline.review(db, ds, body.decisions, body.approve_all_pending)
    return {"dataset_id": ds.id, "status": ds.status, "decisions": final, "warnings": warnings}


# Steps 14-17
@router.post("/{ds_id}/clean")
def clean(
    ds_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ds = get_ds(db, ds_id, user)

    return {
        "dataset_id": ds.id,
        **pipeline.clean(db, ds, user),
        "status": ds.status,
    }


@router.get("/{ds_id}")
def detail(
    ds_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    ds = get_ds(db, ds_id, user)
    st = ds.state or {}

    return {
        "id": ds.id,
        "filename": ds.filename,
        "category": ds.category,
        "purpose": ds.purpose,
        "status": ds.status,

        "inspection": st.get("inspection"),

        "suggested_mappings": st.get("suggested_mappings", []),
        "available_banking_fields": CANONICAL,

        "mappings": st.get("mappings"),

        "post_validation": st.get("post_validation"),
        "cleaning_log": st.get("cleaning_log", []),
        
    }


@router.get("/{ds_id}/profile")
def profile(ds_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ds = get_ds(db, ds_id, user)
    pipeline.require(ds, "analyzed")
    return ds.state["profile"]


@router.get("/{ds_id}/profile/ydata", response_class=HTMLResponse)
def ydata_profile(ds_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ds = get_ds(db, ds_id, user)
    pipeline.require(ds, "analyzed")
    p = ds.state["profile"].get("ydata_report")
    if not p or not Path(p).exists():
        raise HTTPException(404, ds.state["profile"].get("ydata_note") or "YData report not available")
    return HTMLResponse(Path(p).read_text(encoding="utf-8"))


@router.get("/{ds_id}/results")
def results(ds_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ds = get_ds(db, ds_id, user)
    pipeline.require(ds, "analyzed")
    return ds.state["consolidated"]


@router.get("/{ds_id}/recommendations")
def get_recommendations(ds_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ds = get_ds(db, ds_id, user)
    pipeline.require(ds, "recommended")
    return {"recommendations": ds.state["recommendations"], "decisions": ds.state.get("decisions")}


@router.get("/{ds_id}/download")
def download(ds_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ds = get_ds(db, ds_id, user)
    pipeline.require(ds, "cleaned")
    p = Path(ds.state["cleaned_path"])
    return FileResponse(p, filename=f"cleaned_{Path(ds.filename).stem}.xlsx",
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.get("/{ds_id}/report", response_class=HTMLResponse)
def report(ds_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ds = get_ds(db, ds_id, user)
    pipeline.require(ds, "cleaned")
    return HTMLResponse(Path(ds.state["report_path"]).read_text(encoding="utf-8"))

@router.delete("/{ds_id}")
def delete_dataset(ds_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ds = get_ds(db, ds_id, user)
    shutil.rmtree(pipeline.ds_dir(ds.id), ignore_errors=True)
    db.query(LearningHistory).filter(LearningHistory.dataset_id == ds.id).delete()
    db.delete(ds)
    db.commit()
    return {"deleted": ds_id}
