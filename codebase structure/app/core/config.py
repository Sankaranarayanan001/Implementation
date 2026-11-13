import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-secret")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llava")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")