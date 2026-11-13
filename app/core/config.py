from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    secret_key: str = "change-this-secret"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 480
    database_url: str = "sqlite:///./banking_cleaner.db"
    storage_dir: Path = Path("storage")
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:4b"
    llm_enabled: bool = True
    llm_timeout_seconds: int = 120
    # Fast mode avoids expensive/overlapping engines and optional model calls.
    fast_mode: bool = True
    enable_ai_mapping: bool = False
    enable_ai_discovery: bool = False
    enable_ai_recommendations: bool = False
    enable_ydata: bool = False
    enable_great_expectations: bool = False
    llm_num_ctx: int = 8192
    profile_sample_rows: int = 20000
    max_upload_mb: int = 50
    cors_origins: str = "http://localhost:5173,http://localhost:3000"


settings = Settings()
settings.storage_dir.mkdir(parents=True, exist_ok=True)
