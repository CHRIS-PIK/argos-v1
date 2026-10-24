from __future__ import annotations

from fastapi import Header, HTTPException

from app.ingest.keys import CollectorIdentity, KeyStore

keystore = KeyStore()


def require_reader(x_api_key: str | None = Header(default=None)) -> CollectorIdentity:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="missing X-API-Key")
    identity = keystore.authenticate(x_api_key)
    if identity is None:
        raise HTTPException(status_code=401, detail="invalid API key")
    if not identity.has_role("reader"):
        raise HTTPException(status_code=403, detail="API key role cannot read data")
    return identity


def require_admin(x_api_key: str | None = Header(default=None)) -> CollectorIdentity:
    identity = require_reader(x_api_key)
    if not identity.has_role("admin"):
        raise HTTPException(status_code=403, detail="admin role required")
    return identity
