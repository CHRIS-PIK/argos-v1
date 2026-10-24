from __future__ import annotations

import os
from dataclasses import dataclass


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
    ingest_url: str = os.environ["ARGOS_INGEST_URL"].rstrip("/")
    ingest_api_key: str = os.environ["ARGOS_API_KEY"]
    ingest_verify_tls: bool = _bool("ARGOS_INGEST_VERIFY_TLS", True)
    source: str = os.getenv("ARGOS_SOURCE", "aruba-central")
    token_dir: str = os.getenv("TOKEN_DIR", "/data")


settings = Settings()
