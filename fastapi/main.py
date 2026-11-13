from fastapi import FastAPI, UploadFile, File, Form
from contextlib import asynccontextmanager
import httpx

from model import ImageAnswer
from llm import ask_about_image


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(timeout=120)
    yield
    await app.state.client.aclose()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/analyze-image", response_model=ImageAnswer)
async def analyze_image(
    image: UploadFile = File(...),
    question: str = Form(...),
):
    print("\n[1] Request received by FastAPI")
    print(f"    filename = {image.filename}")
    print(f"    question = {question}")

    # FastAPI's job: receive + read the upload
    image_bytes = await image.read()
    print(f"[2] Image read into memory ({len(image_bytes)} bytes)")

    # Delegate the actual AI work to llm_service — this file doesn't know HOW
    # the answer is generated, only that it asks and gets a string back
    print("[3] Sending image + question to LLM service...")
    answer = await ask_about_image(app.state.client, image_bytes, question)
    print(f"[4] Answer received from LLM ({len(answer)} chars)")

    print("[5] Returning response to client\n")

    # FastAPI's job again: shape the response
    return ImageAnswer(
        question=question,
        filename=image.filename,
        answer=answer,
    )

#uvicorn main:app --reload