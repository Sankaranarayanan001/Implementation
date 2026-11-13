from fastapi import FastAPI, UploadFile, File, Form
from contextlib import asynccontextmanager
import httpx
import base64

# -----------------------------
# Setup: shared HTTP client
# -----------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(timeout=120)
    yield
    await app.state.client.aclose()

app = FastAPI(lifespan=lifespan)


# -----------------------------
# Endpoint: upload image + ask a question about it
# -----------------------------
@app.post("/analyze-image")
async def analyze_image(
    image: UploadFile = File(...),
    question: str = Form(...),
):
    # 1. Read the uploaded image bytes
    image_bytes = await image.read()

    # 2. Encode image to base64 (Ollama expects base64 strings)
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    # 3. Send image + question to Ollama's vision model (e.g. llava)
    response = await app.state.client.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "llava",
            "prompt": question,
            "images": [image_b64],
            "stream": False,
        },
    )

    # 4. Extract and return the answer
    data = response.json()
    return {
        "question": question,
        "filename": image.filename,
        "answer": data["response"],
    }


# -----------------------------
# Health check (optional, good for demo)
# -----------------------------
@app.get("/health")
async def health():
    return {"status": "ok"}