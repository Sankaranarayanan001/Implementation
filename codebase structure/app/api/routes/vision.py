from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.deps import get_current_user
from app.models.user import User
from app.services.llm_service import describe_image

router = APIRouter(prefix="/vision", tags=["Vision"])


@router.post("/describe")
def describe(
    text: str = Form("What is in this image?"),
    image: UploadFile = File(...),
    current_user: User = Depends(get_current_user),   # token required
):
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(400, "Please upload an image file")

    image_bytes = image.file.read()
    try:
        answer = describe_image(text, image_bytes)
    except Exception as e:
        raise HTTPException(500, f"LLM error: {e}")

    return {"user": current_user.username, "question": text, "answer": answer}