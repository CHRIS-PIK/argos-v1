from __future__ import annotations

from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.auth import TokenManager
from app.config import settings


class ArubaClient:
    def __init__(self) -> None:
        self.tokens = TokenManager()
        self.session = requests.Session()
        retry = Retry(
            total=5,
            connect=3,
            read=3,
            backoff_factor=1,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def pages(self, path: str, params: dict | None = None):
        params = dict(params or {})
        params.setdefault("limit", settings.aruba_page_limit)
        url = urljoin(settings.aruba_base_url, path.lstrip("/"))
        seen_cursors: set[str] = set()

        while url:
            headers = {
                "Authorization": f"Bearer {self.tokens.get_access_token()}",
                "Accept": "application/json",
            }
            response = self.session.get(
                url,
                headers=headers,
                params=params,
                timeout=60,
                verify=settings.aruba_verify_tls,
            )
            if response.status_code == 401:
                # Força nova autenticação e repete a chamada uma vez.
                from app.auth import TOKEN_FILE

                TOKEN_FILE.unlink(missing_ok=True)
                headers["Authorization"] = f"Bearer {self.tokens.get_access_token()}"
                response = self.session.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=60,
                    verify=settings.aruba_verify_tls,
                )

            response.raise_for_status()
            root = response.json()
            if isinstance(root.get("body"), str):
                import json

                root["body"] = json.loads(root["body"])

            container = root.get("body", root)
            items = container.get("items", []) if isinstance(container, dict) else []
            yield items

            next_value = container.get("next") if isinstance(container, dict) else None

            # Alguns endpoints retornam um objeto com um link completo para a próxima página.
            if isinstance(next_value, dict):
                next_href = next_value.get("href")
                if next_href:
                    url = urljoin(url, str(next_href))
                    params = {}
                    continue
                next_value = None

            # Na API New Central, `next` é um cursor, mesmo quando o valor parece numérico.
            # Portanto, `next=2` não significa `offset=2` e também não deve virar `/v1/2`.
            if next_value not in (None, ""):
                cursor = str(next_value).strip()
                if cursor:
                    if cursor in seen_cursors:
                        break
                    seen_cursors.add(cursor)
                    params.pop("offset", None)
                    params["next"] = cursor
                    continue

            # Fallback apenas para APIs que realmente expõem offset/total sem cursor `next`.
            total = (
                int(container.get("total", container.get("count", len(items))) or 0)
                if isinstance(container, dict)
                else len(items)
            )
            offset = int(params.get("offset", 0))
            if items and offset + len(items) < total:
                params.pop("next", None)
                params["offset"] = offset + len(items)
            else:
                url = ""
