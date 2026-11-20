"""Feeder package (interface A) -> feeder record (interface B): `gridmeta describe`.

The record holds every property that can be computed from the package alone. Unknown values are
left out. An invalid package raises InvalidPackage listing every problem found, one per line.
"""

import json
from pathlib import Path

import jsonschema

from gridmeta.location import load_reference, location_properties
from gridmeta.package import (
    APPLICATION_SPECIFIC,
    check_own_feeder,
    load_provenance,
    load_sanitize,
    load_source,
    load_verify,
)
from gridmeta.record_models import FeederRecord
from gridmeta.stoplight import quality_measurements
from gridmeta.structure import NO_POSITIONS, structural_properties
from gridmeta.vocabulary import CONTEXT_URL, VOCABULARY_VERSION, record_json_schema, vocabulary

NUMBER_RANGES = ("xsd:integer", "xsd:decimal")


class InvalidPackage(ValueError):
    """Every problem of one package, one per line, each naming the file and field."""


def _unconfirmed_zeros(record: dict, provenance, properties: dict) -> list[str]:
    """Model-derived numbers that are 0 while provenance.json says the component's source data is
    missing: the zero is not confirmed, so the value is unknown."""
    # contract 4.5a: booleans are kept.
    unknown = []
    for key, value in record.items():
        entry = properties.get(key, {})
        if entry.get("range") not in NUMBER_RANGES or value != 0 or not entry.get("component"):
            continue
        component = entry["component"].removeprefix("gk:Component.")
        if getattr(provenance.components, component).missing:
            unknown.append(key)
    return unknown


def _collect(problems: list[str], step, *args):
    """Run one independent step; its ValueError joins the list of problems."""
    try:
        return step(*args)
    except ValueError as error:
        problems.append(str(error))
        return None


def build_record(package_dir: Path, reference_dir: Path) -> dict:
    """The feeder record as JSON data, before validation."""
    package_dir = Path(package_dir)
    problems = []
    source_path = package_dir / "source.json"
    source = _collect(problems, load_source, source_path)
    if source is not None:
        _collect(problems, check_own_feeder, source_path, source, package_dir.name)
    provenance = _collect(problems, load_provenance, package_dir / "provenance.json")
    _collect(problems, load_verify, package_dir / "verify.json")
    sanitize_path = package_dir / "sanitize.json"
    sanitize = _collect(problems, load_sanitize, sanitize_path) if sanitize_path.exists() else None
    jsonld_dir = package_dir / "jsonld"
    structure = _collect(problems, structural_properties, jsonld_dir, package_dir.name)
    reference = _collect(problems, load_reference, Path(reference_dir))
    location = None
    if reference is not None:
        service_points = package_dir / "private" / "service_points.csv"
        location = _collect(problems, location_properties, service_points, reference)
    if problems:
        raise InvalidPackage("\n".join(problems))

    # The published context, not an inline one (contract 4.5a).
    record = {
        "@context": CONTEXT_URL,
        "gk:vocabularyVersion": VOCABULARY_VERSION,
        "gk:modelClass": f"gk:ModelClass.{source.model_class}",
        "gk:useCase": f"gk:UseCase.{source.use_case}",
        "gk:state": source.state,
        "gk:multiFeederCompatible": source.multi_feeder_compatible,
        **location,
        **structure,
        "dqv:hasQualityMeasurement": quality_measurements(
            provenance, sanitize, structure["gk:geographicSpecificity"] != NO_POSITIONS
        ),
    }
    if source.use_case == APPLICATION_SPECIFIC:
        record["gk:application"] = [f"gk:Application.{name}" for name in source.applications]
    record = {key: value for key, value in record.items() if value is not None}
    properties = vocabulary()["properties"]
    for key in _unconfirmed_zeros(record, provenance, properties):
        del record[key]
    return record


def describe(package_dir: Path, reference_dir: Path) -> FeederRecord:
    """The feeder record of one package, validated against the generated JSON Schema."""
    record = build_record(package_dir, reference_dir)
    jsonschema.Draft202012Validator(record_json_schema()).validate(record)
    return FeederRecord.model_validate(record)


def record_json(record: FeederRecord) -> str:
    """The record as written by `gridmeta describe`: sorted keys, so a rerun is byte-identical."""
    data = record.model_dump(mode="json", by_alias=True, exclude_none=True)
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
