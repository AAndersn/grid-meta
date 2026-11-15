"""M3: provenance.json -> dqv:hasQualityMeasurement (contract 4.4)."""

import json
from pathlib import Path

import pytest

from gridmeta.package import load_provenance
from gridmeta.package_models import Provenance, Sanitize
from gridmeta.stoplight import quality_measurements

CONTRACT_DIR = Path(__file__).parent / "data" / "contract"
SANITIZE = {
    "tool": "grid-reducer",
    "version": "0.3.0",
    "config_sha256": "0" * 64,
    "reduce": {"transformers": False, "lines": False},
    "layout": {"enabled": True, "obfuscation": "moderate"},
    "noise": {"transformers": "moderate", "lines": "none", "loads": "high", "layout": "none"},
    "rename": True,
}


def example_provenance() -> Provenance:
    return load_provenance(CONTRACT_DIR / "provenance.json")


def by_component(measurements: list[dict]) -> dict[str, dict]:
    return {m["gk:component"].removeprefix("gk:Component."): m for m in measurements}


def with_component(name: str, **entry) -> Provenance:
    data = json.loads((CONTRACT_DIR / "provenance.json").read_text())
    data["components"][name] = {"objects": 0, "inferred": 0, "missing": False, "notes": []} | entry
    return Provenance.model_validate(data)


def test_golden_example():
    """examples/provenance.json + source.json (not sanitised) -> the measurements of record.json."""
    record = json.loads((CONTRACT_DIR / "record.json").read_text())
    measurements = quality_measurements(example_provenance(), None, has_positions=True)
    assert measurements == record["dqv:hasQualityMeasurement"]


@pytest.mark.parametrize(
    "objects, inferred, level, value",
    [
        (100, 20, "Sourced", 0.8),
        (1000, 201, "Sourced", 0.8),  # 0.799 rounds to 0.80, and the threshold is on dqv:value
        (1000, 206, "Inferred", 0.79),
        (8, 1, "Sourced", 0.88),  # 0.875 rounds half up
        (3, 3, "Inferred", 0.0),
    ],
)
def test_threshold_and_rounding(objects, inferred, level, value):
    provenance = with_component("DER", objects=objects, inferred=inferred)
    der = by_component(quality_measurements(provenance, None, True))["DER"]
    assert der["gk:provenanceLevel"] == f"gk:ProvenanceLevel.{level}"
    assert der["dqv:value"] == value


def test_not_present_and_missing():
    provenance = with_component("Protection", notes=["the source confirms there are none"])
    protection = by_component(quality_measurements(provenance, None, True))["Protection"]
    assert protection["gk:provenanceLevel"] == "gk:ProvenanceLevel.NotPresent"
    assert "dqv:value" not in protection
    provenance = with_component("Protection", objects=4, inferred=0, missing=True)
    protection = by_component(quality_measurements(provenance, None, True))["Protection"]
    assert protection["gk:provenanceLevel"] == "gk:ProvenanceLevel.Missing"
    assert "dqv:value" not in protection
    assert "rdfs:comment" not in protection  # no notes


def test_sanitised_package():
    measurements = by_component(
        quality_measurements(example_provenance(), Sanitize.model_validate(SANITIZE), True)
    )
    transformers = measurements["DistributionTransformers"]
    assert transformers["dqv:value"] == 0.0
    assert transformers["gk:provenanceLevel"] == "gk:ProvenanceLevel.Inferred"
    assert transformers["rdfs:comment"].endswith("; differential privacy noise (moderate)")
    assert measurements["Loads"]["rdfs:comment"].endswith("; differential privacy noise (high)")
    assert measurements["Conductors"]["dqv:value"] == 0.36  # lines: none
    coordinates = measurements["Coordinates"]
    assert coordinates["dqv:value"] == 0.0
    assert coordinates["gk:provenanceLevel"] == "gk:ProvenanceLevel.Inferred"
    assert (
        coordinates["rdfs:comment"] == "coordinates replaced by a force-directed layout (moderate)"
    )
    assert measurements["Topology"]["dqv:value"] == 1.0  # not perturbed


def test_layout_noise_follows_the_layout_comment():
    sanitize = SANITIZE | {"noise": SANITIZE["noise"] | {"layout": "low"}}
    coordinates = by_component(
        quality_measurements(example_provenance(), Sanitize.model_validate(sanitize), True)
    )["Coordinates"]
    assert coordinates["rdfs:comment"] == (
        "coordinates replaced by a force-directed layout (moderate); differential privacy noise (low)"
    )


def test_no_layout_keeps_source_coordinates_level():
    sanitize = SANITIZE | {"layout": {"enabled": False, "obfuscation": "none"}}
    coordinates = by_component(
        quality_measurements(example_provenance(), Sanitize.model_validate(sanitize), True)
    )["Coordinates"]
    assert coordinates["gk:provenanceLevel"] == "gk:ProvenanceLevel.Sourced"


def test_noise_leaves_absent_components_alone():
    provenance = with_component("DistributionTransformers")
    transformers = by_component(
        quality_measurements(provenance, Sanitize.model_validate(SANITIZE), True)
    )["DistributionTransformers"]
    assert transformers["gk:provenanceLevel"] == "gk:ProvenanceLevel.NotPresent"


def test_no_positions_makes_coordinates_missing():
    for sanitize in (None, Sanitize.model_validate(SANITIZE)):
        coordinates = by_component(quality_measurements(example_provenance(), sanitize, False))[
            "Coordinates"
        ]
        assert coordinates["gk:provenanceLevel"] == "gk:ProvenanceLevel.Missing"
        assert "dqv:value" not in coordinates
        assert coordinates["rdfs:comment"].endswith("the shipped data file has no positions")
