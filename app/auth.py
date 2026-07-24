from __future__ import annotations
import json
import os
import time
from pathlib import Path
import fcntl
import requests
from app.config import settings

TOKEN_FILE = Path("/data/token.json")
LOCK_FILE = Path("/data/token.lock")


class TokenManager:
    def _load(self) -> dict:
        if not TOKEN_FILE.exists():
            return {}
        try:
            return json.loads(TOKEN_FILE.read_text())
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self, data: dict) -> None:
        tmp = TOKEN_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        os.replace(tmp, TOKEN_FILE)

    def get_access_token(self) -> str:
        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOCK_FILE.open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            token = self._load()
            if token.get("access_token") and token.get("expires_at", 0) > time.time() + 120:
                return token["access_token"]
            return self._renew()

    def _renew(self) -> str:
        payload = {
            "grant_type": "client_credentials",
            "client_id": settings.aruba_client_id,
            "client_secret": settings.aruba_client_secret,
        }
        response = requests.post(
            settings.aruba_auth_url,
            data=payload,
            timeout=30,
            verify=settings.aruba_verify_tls,
        )
        response.raise_for_status()
        data = response.json()
        expires_in = int(data.get("expires_in", 3600))
        saved = {
            "access_token": data["access_token"],
            "expires_at": time.time() + expires_in,
        }
        self._save(saved)
        return saved["access_token"]
