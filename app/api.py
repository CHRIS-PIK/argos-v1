from __future__ import annotations
from urllib.parse import urljoin, urlparse, parse_qs
import requests
from app.auth import TokenManager
from app.config import settings

class ArubaClient:
    def __init__(self) -> None:
        self.tokens = TokenManager()
        self.session = requests.Session()

    def pages(self, path: str, params: dict | None = None):
        params = dict(params or {})
        params.setdefault("limit", settings.aruba_page_limit)
        url = urljoin(settings.aruba_base_url, path.lstrip("/"))
        while url:
            headers = {"Authorization": f"Bearer {self.tokens.get_access_token()}", "Accept": "application/json"}
            response = self.session.get(url, headers=headers, params=params, timeout=60, verify=settings.aruba_verify_tls)
            if response.status_code == 401:
                # força nova autenticação no próximo ciclo
                from app.auth import TOKEN_FILE
                TOKEN_FILE.unlink(missing_ok=True)
                headers["Authorization"] = f"Bearer {self.tokens.get_access_token()}"
                response = self.session.get(url, headers=headers, params=params, timeout=60, verify=settings.aruba_verify_tls)
            response.raise_for_status()
            root = response.json()
            if isinstance(root.get("body"), str):
                import json
                root["body"] = json.loads(root["body"])
            container = root.get("body", root)
            items = container.get("items", []) if isinstance(container, dict) else []
            yield items
            next_value = container.get("next") if isinstance(container, dict) else None
            if isinstance(next_value, dict):
                next_value = next_value.get("href")
            if next_value:
                url = urljoin(url, str(next_value))
                params = {}
                continue
            # fallback para APIs com offset/total
            total = int(container.get("total", container.get("count", len(items))) or 0) if isinstance(container, dict) else len(items)
            offset = int(params.get("offset", 0))
            if items and offset + len(items) < total:
                params["offset"] = offset + len(items)
            else:
                url = ""
