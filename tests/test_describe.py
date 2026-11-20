"""M4: `gridmeta describe` and describe(), on synthetic packages."""

import json
from pathlib import Path

import cimprofiles.cim18.cim18v17 as cim
import pytest
from click.testing import CliRunner

from gridmeta.cli.cli import cli
from gridmeta.describe import InvalidPackage, describe, record_json
from gridmeta.structure import objects, read_models, size_distribution
from gridmeta.testing import EXAMPLE_SERVICE_POINTS, write_reference_dir
from synthetic import (
    CONTRACT_DIR,
    MODEL_ID,
    FeederBuilder,
    example_feeder,
    write_json,
    write_package,
)

EXAMPLE_RECORD = json.loads((CONTRACT_DIR / "record.json").read_text())
# The numbers the synthetic example feeder defines (tests/synthetic.py), where examples/record.json
# has those of a real-sized feeder.
MODEL_NUMBERS = {
    "gk:feederLength": 2.5,
    "gk:undergroundShare": 0.2,
    "gk:loadCount": 3,
    "gk:customerCount": 3,
    "gk:loadSizeDistribution": size_distribution([2.0, 3.0, 12.0]),
    "gk:dgCount": 1,
    "gk:dgCapacityAC": 7.6,
    "gk:dgSizeDistribution": size_distribution([7.6]),
    "gk:fuseCount": 1,
    "gk:recloserCount": 1,
    "gk:regulatorCount": 0,
    "gk:capacitorCount": 1,
}


@pytest.fixture
def reference_dir(tmp_path) -> Path:
    return write_reference_dir(tmp_path / "reference")


@pytest.fixture
def package(tmp_path) -> Path:
    return write_package(tmp_path / "packages", example_feeder(), EXAMPLE_SERVICE_POINTS)


def record_data(package: Path, reference_dir: Path) -> dict:
    return json.loads(record_json(describe(package, reference_dir)))


def test_reproduces_the_example_record(package, reference_dir):
    record = record_data(package, reference_dir)
    assert set(record) == set(EXAMPLE_RECORD)
    for key, expected in EXAMPLE_RECORD.items():
        assert record[key] == MODEL_NUMBERS.get(key, expected), key


def test_cli_output_is_sorted_and_byte_identical(package, reference_dir, tmp_path):
    runner = CliRunner()
    outputs = []
    for name in ("first.json", "second.json"):
        output = tmp_path / name
        result = runner.invoke(
            cli,
            ["describe", str(package), "-o", str(output)],
            env={"GRIDMETA_REFERENCE_DIR": str(reference_dir)},
        )
        assert result.exit_code == 0, result.output
        outputs.append(output.read_bytes())
    assert outputs[0] == outputs[1]
    record = json.loads(outputs[0])
    assert list(record) == sorted(record)


def test_cli_writes_to_standard_output(package, reference_dir):
    result = CliRunner().invoke(
        cli, ["describe", str(package), "--reference-dir", str(reference_dir)]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["gk:state"] == "VT"


def test_invalid_package_lists_every_problem(package, reference_dir):
    source = json.loads((package / "source.json").read_text())
    write_json(package / "source.json", source | {"state": "Vermont", "model_class": "Synthetic"})
    provenance = json.loads((package / "provenance.json").read_text())
    del provenance["components"]["TimeSeries"]
    write_json(package / "provenance.json", provenance)
    (package / "verify.json").unlink()
    (package / "jsonld" / "feeder_VT-0a1b2c3d4e.jsonld").unlink()
    (package / "private" / "service_points.csv").unlink()
    result = CliRunner().invoke(
        cli, ["describe", str(package), "--reference-dir", str(reference_dir)]
    )
    assert result.exit_code != 0
    for problem in [
        r"source.json: state: ",
        r"source.json: model_class: ",
        r"provenance.json: components.TimeSeries: Field required",
        r"verify.json: file is missing",
        r"feeder_VT-0a1b2c3d4e.jsonld: file is missing",
        r"service_points.csv: file is missing",
    ]:
        assert problem in result.output, problem


def test_unmapped_own_feeder_is_an_invalid_package(package, reference_dir):
    source = json.loads((package / "source.json").read_text())
    write_json(package / "source.json", source | {"boundary_feeders": {"cn": "VT-9999999999"}})
    with pytest.raises(
        InvalidPackage, match=r"no boundary node maps to the package's model_id VT-0a1b2c3d4e"
    ):
        describe(package, reference_dir)


def test_missing_reference_dir_is_an_error(package):
    result = CliRunner().invoke(
        cli, ["describe", str(package)], env={"GRIDMETA_REFERENCE_DIR": ""}
    )
    assert result.exit_code != 0
    assert "--reference-dir" in result.output


def test_application_specific(package, reference_dir):
    source = json.loads((package / "source.json").read_text())
    change = {"use_case": "ApplicationSpecific", "applications": ["Protection", "DERManagement"]}
    write_json(package / "source.json", source | change)
    record = record_data(package, reference_dir)
    assert record["gk:useCase"] == "gk:UseCase.ApplicationSpecific"
    assert record["gk:application"] == [
        "gk:Application.Protection",
        "gk:Application.DERManagement",
    ]


def test_zero_of_a_missing_component_is_left_out(tmp_path, reference_dir):
    feeder = FeederBuilder()
    feeder.line("head", "n1", 1.0)
    feeder.center_tap("n1", "s1")
    feeder.load("s1", 2.0, kv=0.24)
    feeder.position("urn:ogc:def:crs:OGC:1.3:CRS84")
    package = write_package(tmp_path / "packages", feeder, EXAMPLE_SERVICE_POINTS)
    provenance = json.loads((package / "provenance.json").read_text())
    provenance["components"]["DER"] = {"objects": 0, "inferred": 0, "missing": True, "notes": []}
    write_json(package / "provenance.json", provenance)
    record = record_data(package, reference_dir)
    assert "gk:dgCount" not in record and "gk:dgCapacityAC" not in record
    assert record["gk:sectionalizerCount"] == 0  # Protection is not missing: a confirmed zero


def test_sanitised_package_without_positions(tmp_path, reference_dir):
    feeder = FeederBuilder()
    feeder.line("head", "n1", 1.0)
    feeder.load("n1", 2.0)
    sanitize = {
        "tool": "grid-reducer",
        "version": "0.3.0",
        "config_sha256": "0" * 64,
        "reduce": {"transformers": False, "lines": False},
        "layout": {"enabled": False, "obfuscation": "none"},
        "noise": {"transformers": "none", "lines": "low", "loads": "none", "layout": "none"},
        "rename": True,
    }
    package = write_package(tmp_path / "packages", feeder, EXAMPLE_SERVICE_POINTS, sanitize)
    record = record_data(package, reference_dir)
    levels = {
        m["gk:component"]: m["gk:provenanceLevel"] for m in record["dqv:hasQualityMeasurement"]
    }
    assert levels["gk:Component.Conductors"] == "gk:ProvenanceLevel.Inferred"
    assert levels["gk:Component.Coordinates"] == "gk:ProvenanceLevel.Missing"
    assert record["gk:geographicSpecificity"] == "gk:GeographicSpecificity.None"
    assert record["gk:secondaryModeling"] == "gk:SecondaryModeling.None"


def test_area_objects_change_nothing(tmp_path, package, reference_dir):
    """A 0.6.0 package of a tied distribution area (contract 3.5) also carries the area frame's
    ConnectedAreas, its other Feeders, the other Substation and the tie, the sibling feeders'
    breakers in the substation frame, and their head nodes and both sides of the tie in the
    boundary. The far side has only the open tie's terminal. None of it changes a count or the
    coordinates rule: the record equals that of the same feeder without them."""
    feeder = example_feeder()
    tie = feeder.area(own_node="n2")
    tied = write_package(tmp_path / "tied", feeder, EXAMPLE_SERVICE_POINTS)
    network, feeder_frame, substation_frame, area_frame = read_models(tied / "jsonld", MODEL_ID)
    assert len(objects(network, cim.ConnectedArea, area_frame)) == 6
    assert len(objects(network, cim.Feeder, area_frame)) == 4
    assert len(objects(network, cim.Substation, area_frame)) == 2
    assert area_frame.holds(tie) and not feeder_frame.holds(tie)
    assert len(objects(network, cim.Breaker, substation_frame)) == 3
    (far,) = [node for node in objects(network, cim.ConnectivityNode) if node.name == "far"]
    assert [terminal.ConductingEquipment.mRID for terminal in far.Terminals] == [tie.mRID]
    assert isinstance(far.ConnectivityNodeContainer, cim.ConnectedArea)
    assert not feeder_frame.holds(far) and not substation_frame.holds(far)
    assert record_data(tied, reference_dir) == record_data(package, reference_dir)


def test_restated_objects_are_one_object(tmp_path):
    """A base voltage that every frame declares, and the Substation that the area frame
    restates, load as one object each (contract 3.5 rule 1)."""
    feeder = example_feeder()
    feeder.area(own_node="n2")
    jsonld_dir = feeder.write(tmp_path / "jsonld")
    network, *frames = read_models(jsonld_dir, MODEL_ID)
    (primary,) = [
        voltage
        for voltage in objects(network, cim.BaseVoltage)
        if voltage.nominalVoltage.to("kV") == 12.47
    ]
    assert all(frame.holds(primary) for frame in frames)
    assert len(objects(network, cim.Substation)) == 2


def test_describe_raises_invalid_package(tmp_path, reference_dir):
    (tmp_path / "VT-0a1b2c3d4e").mkdir()
    with pytest.raises(InvalidPackage, match=r"source\.json: file is missing"):
        describe(tmp_path / "VT-0a1b2c3d4e", reference_dir)
