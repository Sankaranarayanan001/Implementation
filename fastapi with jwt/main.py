from dotenv import load_dotenv
load_dotenv()

import sqlite3
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from contextlib import asynccontextmanager
import httpx

from db import init_db, get_db
from model import ImageAnswer, UserCreate, UserOut, Token
from llm import ask_about_image
import auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.client = httpx.AsyncClient(timeout=120)
    yield
    await app.state.client.aclose()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/register", response_model=UserOut)
async def register(user_in: UserCreate, conn=Depends(get_db)):
    try:
        cur = conn.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (user_in.username, user_in.password),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Username already taken")

    return UserOut(id=cur.lastrowid, username=user_in.username, is_active=True)


@app.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), conn=Depends(get_db)):
    user = auth.authenticate_user(conn, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    return Token(access_token=auth.create_access_token(user["username"]))


@app.post("/analyze-image", response_model=ImageAnswer)
async def analyze_image(
    image: UploadFile = File(...),
    question: str = Form(...),
    current_user=Depends(auth.get_current_user),
):
    image_bytes = await image.read()
    answer = await ask_about_image(app.state.client, image_bytes, question)
    return ImageAnswer(question=question, filename=image.filename, answer=answer)