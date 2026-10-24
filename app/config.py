from __future__ import annotations
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    db_host: str = os.getenv("DB_HOST", "127.0.0.1")
    db_port: int = int(os.getenv("DB_PORT", "3306"))
    db_name: str = os.getenv("DB_NAME", "aruba_reporting")
    db_user: str = os.getenv("DB_USER", "aruba_ingestor")
    db_password: str = os.environ["DB_PASSWORD"]
    retention_days: int = int(os.getenv("RETENTION_DAYS", "90"))


settings = Settings()
