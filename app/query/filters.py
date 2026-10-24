from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, Query, Request

from app.ingest.keys import CollectorIdentity

DIM_KEY = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
DIM_PREFIX = "dim."
MAX_DIMENSIONS = 8


@dataclass
class Filters:
    """Filtros comuns de entidades e eventos. Tudo vira parâmetro nomeado do ClickHouse;
    nenhum valor vindo do cliente é concatenado no SQL."""

    event_type: str | None = None
    source: str | None = None
    status: str | None = None
    q: str | None = None
    entity_id: str | None = None
    dimensions: dict[str, str] = field(default_factory=dict)

    def where(self, identity: CollectorIdentity) -> tuple[list[str], dict[str, Any]]:
        # O tenant vem sempre da chave autenticada, nunca do pedido.
        clauses = ["tenant_id = {tenant:String}"]
        params: dict[str, Any] = {"tenant": identity.tenant_id}

        if "*" not in identity.allowed_event_types:
            clauses.append("event_type IN {allowed:Array(String)}")
            params["allowed"] = sorted(identity.allowed_event_types)

        for column in ("event_type", "source", "status", "entity_id"):
            value = getattr(self, column)
            if value:
                clauses.append(f"{column} = {{{column}:String}}")
                params[column] = value

        if self.q:
            clauses.append(
                "(positionCaseInsensitive(name, {q:String}) > 0"
                " OR positionCaseInsensitive(entity_id, {q:String}) > 0)"
            )
            params["q"] = self.q

        for index, (key, value) in enumerate(sorted(self.dimensions.items())):
            clauses.append(f"dimensions[{{dk{index}:String}}] = {{dv{index}:String}}")
            params[f"dk{index}"] = key
            params[f"dv{index}"] = value

        return clauses, params


def dimensions_from_query(query_params: Any) -> dict[str, str]:
    """Lê `dim.<chave>=<valor>` da query string."""
    dims: dict[str, str] = {}
    for name, value in query_params.items():
        if not name.startswith(DIM_PREFIX):
            continue
        key = name[len(DIM_PREFIX):]
        if not DIM_KEY.match(key):
            raise HTTPException(status_code=422, detail=f"invalid dimension name: {key!r}")
        dims[key] = value
    if len(dims) > MAX_DIMENSIONS:
        raise HTTPException(status_code=422, detail=f"at most {MAX_DIMENSIONS} dimension filters")
    return dims


def encode_cursor(values: list[Any]) -> str:
    raw = json.dumps(values, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str, size: int) -> list[Any]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        values = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except Exception:
        raise HTTPException(status_code=422, detail="invalid cursor") from None
    if not isinstance(values, list) or len(values) != size:
        raise HTTPException(status_code=422, detail="invalid cursor")
    return values


def common_filters(
    request: Request,
    event_type: str | None = Query(default=None, max_length=64),
    source: str | None = Query(default=None, max_length=64),
    status: str | None = Query(default=None, max_length=128),
    q: str | None = Query(default=None, max_length=128, description="Busca em nome e id"),
) -> Filters:
    return Filters(
        event_type=event_type,
        source=source,
        status=status,
        q=q,
        dimensions=dimensions_from_query(request.query_params),
    )
