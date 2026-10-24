from __future__ import annotations

import logging
import time
from datetime import datetime

import requests

from config import settings

log = logging.getLogger(__name__)

RETRYABLE = {408, 429, 500, 502, 503, 504}


class IngestRejected(Exception):
    """A plataforma recusou o lote de forma definitiva (4xx); reenviar não adianta."""


class IngestClient:
    def __init__(self, max_attempts: int = 5, base_delay: float = 2.0) -> None:
        self.url = f"{settings.ingest_url}/v1/events"
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.session = requests.Session()
        self.session.headers["X-API-Key"] = settings.ingest_api_key

    def send(
        self,
        event_type: str,
        items: list[dict],
        batch_id: str,
        page: int,
        collected_at: datetime,
        schema_version: str = "1",
    ) -> bool:
        """Envia um lote. Retorna True se aceito como novo, False se duplicado."""
        body = {
            "source": settings.source,
            "event_type": event_type,
            "schema_version": schema_version,
            "batch_id": batch_id,
            "page": page,
            "collected_at": collected_at.isoformat() + "Z",
            "items": items,
        }
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.session.post(
                    self.url,
                    json=body,
                    timeout=60,
                    verify=settings.ingest_verify_tls,
                )
            except requests.RequestException as exc:
                self._backoff(attempt, f"{type(exc).__name__}")
                continue

            if response.status_code == 202:
                return not response.json().get("duplicate", False)
            if response.status_code in RETRYABLE:
                delay = response.headers.get("Retry-After")
                self._backoff(attempt, f"http {response.status_code}", delay)
                continue
            raise IngestRejected(f"http {response.status_code}: {response.text[:500]}")

        raise RuntimeError(
            f"ingest unavailable after {self.max_attempts} attempts event_type={event_type}"
        )

    def _backoff(self, attempt: int, reason: str, retry_after: str | None = None) -> None:
        if attempt >= self.max_attempts:
            return
        delay = self.base_delay * (2 ** (attempt - 1))
        if retry_after and retry_after.isdigit():
            delay = max(delay, float(retry_after))
        log.warning("ingest retry attempt=%s reason=%s sleep=%.1fs", attempt, reason, delay)
        time.sleep(min(delay, 60))
