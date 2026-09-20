from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DESTINATION = "Singapore"
LATITUDE = 1.3521
LONGITUDE = 103.8198
TIMEZONE = "Asia/Singapore"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRAVEL_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    google_api_key: str = Field(default="", validation_alias="GOOGLE_API_KEY")

    model: str = "gemini-3.5-flash"
    max_tokens: int = 8000

    embedding_model: str = "BAAI/bge-small-en-v1.5"

    chunk_size: int = 1000
    chunk_overlap: int = 150

    retrieval_k: int = 6
    retrieval_fetch_k: int = 20
    retrieval_score_threshold: float = 0.20

    data_dir: Path = PROJECT_ROOT / "data"
    vectorstore_dir: Path = PROJECT_ROOT / "vectorstore" / "singapore"

    @property
    def sources_file(self) -> Path:
        return self.data_dir / "sources.yaml"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"


settings = Settings()
