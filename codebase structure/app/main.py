from fastapi import FastAPI

from app.db.database import Base, engine
from app.models import user  # noqa: F401  (registers the table)
from app.api.routes import auth, vision

Base.metadata.create_all(bind=engine)

app = FastAPI(title="LLM Vision App")

app.include_router(auth.router)
app.include_router(vision.router)   