from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from pydantic import BaseModel, Field, field_validator

NAME_PATTERN = r"^[a-z0-9][a-z0-9._-]{0,63}$"
SCHEMA_FILE = re.compile(r"^(?P<event_type>[a-z0-9][a-z0-9._-]*)\.v(?P<version>[0-9]+)\.json$")


class EventBatch(BaseModel):
    """Envelope de um lote de eventos enviado por um coletor."""

    source: str = Field(pattern=NAME_PATTERN, description="Sistema de origem, ex.: aruba-central")
    event_type: str = Field(pattern=NAME_PATTERN, description="Tipo de evento, ex.: aps")
    schema_version: str = Field(default="1", pattern=r"^[0-9]+$")
    batch_id: str | None = Field(
        default=None,
        max_length=128,
        description="Chave de idempotência do lote; reenvios com o mesmo id são ignorados.",
    )
    page: int = Field(default=1, ge=1)
    collected_at: datetime | None = None
    items: list[dict[str, Any]] = Field(min_length=1)

    @field_validator("schema_version", mode="before")
    @classmethod
    def _version_as_text(cls, value: Any) -> Any:
        return str(value) if isinstance(value, int) else value


class SchemaRegistry:
    """Carrega JSON Schemas de `<event_type>.v<N>.json` de um diretório.

    Um event_type só é aceito se houver schema registrado para ele. Para criar um
    tipo novo basta adicionar o arquivo (em Kubernetes, via ConfigMap) e reiniciar.
    """

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._validators: dict[tuple[str, str], Draft202012Validator] = {}
        self._load()

    def _load(self) -> None:
        for path in sorted(self.directory.glob("*.json")):
            match = SCHEMA_FILE.match(path.name)
            if not match:
                continue
            schema = json.loads(path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            key = (match["event_type"], match["version"])
            self._validators[key] = Draft202012Validator(schema)

    def has(self, event_type: str, version: str) -> bool:
        return (event_type, version) in self._validators

    def catalog(self) -> list[dict[str, str]]:
        return [
            {"event_type": event_type, "schema_version": version}
            for event_type, version in sorted(self._validators)
        ]

    def validate(self, event_type: str, version: str, items: list[dict[str, Any]]) -> list[str]:
        """Retorna a lista de erros (vazia se válido), limitada para não inflar a resposta."""
        validator = self._validators[(event_type, version)]
        errors: list[str] = []
        for index, item in enumerate(items):
            for error in validator.iter_errors(item):
                location = "/".join(str(part) for part in error.absolute_path) or "(item)"
                errors.append(f"items[{index}] {location}: {error.message}")
                if len(errors) >= 20:
                    return errors
        return errors


def default_registry() -> SchemaRegistry:
    directory = os.getenv("SCHEMAS_DIR") or str(Path(__file__).parent / "schemas")
    return SchemaRegistry(Path(directory))
