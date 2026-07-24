from __future__ import annotations
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool = True) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    aruba_base_url: str = os.environ["ARUBA_BASE_URL"].rstrip("/") + "/"
    aruba_auth_url: str = os.environ["ARUBA_AUTH_URL"]
    aruba_client_id: str = os.environ["ARUBA_CLIENT_ID"]
    aruba_client_secret: str = os.environ["ARUBA_CLIENT_SECRET"]
    aruba_verify_tls: bool = _bool("ARUBA_VERIFY_TLS", True)
    aruba_page_limit: int = int(os.getenv("ARUBA_PAGE_LIMIT", "1000"))
    db_host: str = os.getenv("DB_HOST", "127.0.0.1")
    db_port: int = int(os.getenv("DB_PORT", "3306"))
    db_name: str = os.getenv("DB_NAME", "aruba_reporting")
    db_user: str = os.getenv("DB_USER", "aruba_ingestor")
    db_password: str = os.environ["DB_PASSWORD"]
    retention_days: int = int(os.getenv("RETENTION_DAYS", "90"))


settings = Settings()
