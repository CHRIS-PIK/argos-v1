from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class Mapping:
    """Como extrair os campos canônicos de um item. Declarado no schema, em `x-argos`.

    Cada campo aceita uma lista de caminhos candidatos (o primeiro preenchido vence);
    caminhos aninhados usam ponto, ex.: "device.serial".
    """

    entity_id: tuple[str, ...] = ("id",)
    name: tuple[str, ...] = ()
    status: tuple[str, ...] = ()
    dimensions: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_schema(cls, schema: dict[str, Any]) -> "Mapping":
        raw = schema.get("x-argos", {})

        def paths(key: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
            value = raw.get(key)
            if value is None:
                return default
            return (value,) if isinstance(value, str) else tuple(value)

        return cls(
            entity_id=paths("entity_id", ("id",)),
            name=paths("name"),
            status=paths("status"),
            dimensions=dict(raw.get("dimensions", {})),
        )


@dataclass(frozen=True)
class Resolved:
    entity_id: str
    name: str
    status: str
    dimensions: dict[str, str]


def _lookup(item: dict[str, Any], path: str) -> Any:
    current: Any = item
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _first(item: dict[str, Any], paths: tuple[str, ...]) -> str:
    for path in paths:
        value = _lookup(item, path)
        if value not in (None, "") and not isinstance(value, (dict, list)):
            return str(value)
    return ""


def resolve(mapping: Mapping, item: dict[str, Any]) -> Resolved | None:
    """Aplica o mapeamento a um item. Retorna None se não houver entity_id."""
    entity_id = _first(item, mapping.entity_id)
    if not entity_id:
        return None
    dimensions = {
        key: value
        for key, path in mapping.dimensions.items()
        if (value := _first(item, (path,)))
    }
    return Resolved(
        entity_id=entity_id,
        name=_first(item, mapping.name),
        status=_first(item, mapping.status),
        dimensions=dimensions,
    )


class SchemaRegistry:
    """Carrega JSON Schemas de `<event_type>.v<N>.json` (busca recursiva) em um ou mais diretórios.

    Um event_type só é aceito se houver schema registrado para ele. Para criar um tipo
    novo basta adicionar o arquivo (em Kubernetes, via ConfigMap) e reiniciar. O schema
    valida o formato do item e o bloco `x-argos` diz como extrair os campos canônicos.
    """

    def __init__(self, *directories: Path) -> None:
        self.directories = directories
        self._validators: dict[tuple[str, str], Draft202012Validator] = {}
        self._mappings: dict[tuple[str, str], Mapping] = {}
        for directory in directories:
            self._load(directory)

    def _load(self, directory: Path) -> None:
        if not directory.is_dir():
            return
        for path in sorted(directory.rglob("*.json")):
            match = SCHEMA_FILE.match(path.name)
            if not match:
                continue
            schema = json.loads(path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            key = (match["event_type"], match["version"])
            self._validators[key] = Draft202012Validator(schema)
            self._mappings[key] = Mapping.from_schema(schema)

    def has(self, event_type: str, version: str) -> bool:
        return (event_type, version) in self._validators

    def mapping(self, event_type: str, version: str) -> Mapping:
        return self._mappings[(event_type, version)]

    def catalog(self) -> list[dict[str, str]]:
        return [
            {"event_type": event_type, "schema_version": version}
            for event_type, version in sorted(self._validators)
        ]

    def validate(self, event_type: str, version: str, items: list[dict[str, Any]]) -> list[str]:
        """Retorna a lista de erros (vazia se válido), limitada para não inflar a resposta."""
        validator = self._validators[(event_type, version)]
        mapping = self._mappings[(event_type, version)]
        errors: list[str] = []
        for index, item in enumerate(items):
            for error in validator.iter_errors(item):
                location = "/".join(str(part) for part in error.absolute_path) or "(item)"
                errors.append(f"items[{index}] {location}: {error.message}")
            if resolve(mapping, item) is None:
                errors.append(
                    f"items[{index}] entity_id: none of {list(mapping.entity_id)} is present"
                )
            if len(errors) >= 20:
                return errors[:20]
        return errors


def default_registry() -> SchemaRegistry:
    directories = [Path(__file__).parent / "schemas"]
    extra = os.getenv("SCHEMAS_DIR", "")
    directories += [Path(part) for part in extra.split(os.pathsep) if part]
    return SchemaRegistry(*directories)
