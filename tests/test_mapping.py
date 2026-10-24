from __future__ import annotations

from app.ingest.contract import Mapping, resolve


def test_first_present_path_wins_and_nested_paths_work():
    mapping = Mapping(
        entity_id=("uuid", "device.serial"),
        name=("label",),
        status=("state.current",),
        dimensions={"site": "location.site"},
    )
    item = {"device": {"serial": "SN1"}, "label": "Core", "state": {"current": "up"},
            "location": {"site": "HQ"}}
    resolved = resolve(mapping, item)
    assert (resolved.entity_id, resolved.name, resolved.status) == ("SN1", "Core", "up")
    assert resolved.dimensions == {"site": "HQ"}


def test_missing_entity_id_returns_none():
    assert resolve(Mapping(entity_id=("id",)), {"name": "x"}) is None


def test_empty_and_structured_values_are_ignored():
    mapping = Mapping(entity_id=("id", "alt"))
    assert resolve(mapping, {"id": "", "alt": "A"}).entity_id == "A"
    assert resolve(mapping, {"id": {"x": 1}}) is None


def test_mapping_from_schema_defaults():
    mapping = Mapping.from_schema({"x-argos": {"entity_id": "id", "dimensions": {"d": "p"}}})
    assert mapping.entity_id == ("id",)
    assert mapping.dimensions == {"d": "p"}
    assert Mapping.from_schema({}).entity_id == ("id",)
