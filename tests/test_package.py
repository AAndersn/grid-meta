"""Interface A loaders and models."""

import json
import re
from pathlib import Path

import pytest
import yaml

from generate import GK_SCHEMA, PACKAGE_SCHEMA
from gridmeta.package import (
    check_own_feeder,
    OPTIONAL_VERIFY_COUNTS,
    load_provenance,
    load_sanitize,
    load_source,
    load_verify,
)

CONTRACT_DIR = Path(__file__).parent / "data" / "contract"
SANITIZE = {
    "tool": "grid-reducer",
    "version": "0.3.0",
    "config_sha256": "0" * 64,
    "reduce": {"transformers": False, "lines": False},
    "layout": {"enabled": True, "obfuscation": "moderate"},
    "noise": {"transformers": "moderate", "lines": "none", "loads": "moderate", "layout": "none"},
    "rename": True,
}


def read_example(name: str) -> dict:
    return json.loads((CONTRACT_DIR / name).read_text())


def write_json(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data))
    return path


def test_examples_load():
    source = load_source(CONTRACT_DIR / "source.json")
    assert source.state == "VT"
    assert source.model_scope == "9f8e7d6c5b"
    assert source.pipeline.tools.cim_profiles == "0.2.0"
    assert source.pipeline.tools.opendssdirect_py == "0.10.0"
    provenance = load_provenance(CONTRACT_DIR / "provenance.json")
    assert provenance.components.DistributionTransformers.inferred == 330
    assert provenance.components.Secondary.missing
    verify = load_verify(CONTRACT_DIR / "verify.json")
    assert verify.status == "PASS"
    assert verify.exported_from == "jsonld/"
    assert source.boundary_feeders["cn_head_example_1"] == "VT-0a1b2c3d4e"
    assert source.feeder_area == "area_f_example_1"
    assert source.distribution_area == "Example Distribution Area"


def test_sanitize_loads(tmp_path):
    sanitize = load_sanitize(write_json(tmp_path / "sanitize.json", SANITIZE))
    assert sanitize.noise.loads == "moderate"


def test_shared_enumerations_match_gk():
    gk_enums = yaml.safe_load(GK_SCHEMA.read_text())["enums"]
    package = yaml.safe_load(PACKAGE_SCHEMA.read_text())
    for name in ["ModelClass", "UseCase", "Application"]:
        assert list(package["enums"][name]["permissible_values"]) == list(
            gk_enums[name]["permissible_values"]
        )
    components = package["classes"]["Components"]["attributes"]
    assert list(components) == list(gk_enums["Component"]["permissible_values"])


def test_missing_component_names_file_and_field(tmp_path):
    provenance = read_example("provenance.json")
    del provenance["components"]["TimeSeries"]
    path = write_json(tmp_path / "provenance.json", provenance)
    with pytest.raises(ValueError, match=r"provenance\.json.*TimeSeries"):
        load_provenance(path)


def test_inferred_above_objects_is_rejected(tmp_path):
    provenance = read_example("provenance.json")
    provenance["components"]["DER"]["inferred"] = 75
    path = write_json(tmp_path / "provenance.json", provenance)
    with pytest.raises(ValueError, match=r"components\.DER\.inferred"):
        load_provenance(path)


@pytest.mark.parametrize(
    "change, field",
    [
        ({"use_case": "ApplicationSpecific"}, "applications"),
        ({"applications": ["Protection"]}, "applications"),
        ({"contract_version": "0.6.0"}, "contract_version"),
        ({"distribution_area": 5}, "distribution_area"),
        ({"feeder_area": ""}, "feeder_area"),
        ({"feeder_area": " "}, "feeder_area"),
        ({"state": "Vermont"}, "state"),
        ({"model_class": "Synthetic"}, "model_class"),
        ({"forbidden_strings": []}, "forbidden_strings"),
    ],
)
def test_invalid_source_is_rejected(tmp_path, change, field):
    path = write_json(tmp_path / "source.json", read_example("source.json") | change)
    with pytest.raises(ValueError, match=rf"source\.json.*{field}"):
        load_source(path)


def test_application_specific_source_loads(tmp_path):
    change = {"use_case": "ApplicationSpecific", "applications": ["Protection"]}
    path = write_json(tmp_path / "source.json", read_example("source.json") | change)
    assert load_source(path).applications == ["Protection"]


@pytest.mark.parametrize("field", OPTIONAL_VERIFY_COUNTS)
def test_optional_count_is_zero_when_absent(tmp_path, field):
    assert getattr(load_verify(CONTRACT_DIR / "verify.json"), field) == 0
    verify = read_example("verify.json")
    del verify[field]
    assert getattr(load_verify(write_json(tmp_path / "verify.json", verify)), field) == 0
    verify[field] = 3
    assert getattr(load_verify(write_json(tmp_path / "verify.json", verify)), field) == 3


@pytest.mark.parametrize("value", [-1, None, 1.5, "two"])
@pytest.mark.parametrize("field", OPTIONAL_VERIFY_COUNTS)
def test_invalid_optional_count_is_rejected(tmp_path, field, value):
    path = write_json(tmp_path / "verify.json", read_example("verify.json") | {field: value})
    with pytest.raises(ValueError, match=rf"verify\.json: {field}"):
        load_verify(path)


@pytest.mark.parametrize("field", OPTIONAL_VERIFY_COUNTS)
def test_null_optional_count_names_the_rule(tmp_path, field):
    path = write_json(tmp_path / "verify.json", read_example("verify.json") | {field: None})
    with pytest.raises(ValueError, match=rf"verify\.json: {field}: must be an integer"):
        load_verify(path)


def test_unknown_key_is_rejected(tmp_path):
    path = write_json(tmp_path / "verify.json", read_example("verify.json") | {"vpu_min": 0.9})
    with pytest.raises(ValueError, match=r"verify\.json.*vpu_min"):
        load_verify(path)


@pytest.mark.parametrize("version", ["0.7.0", "0.7.9"])
def test_same_major_minor_is_accepted(tmp_path, version):
    source = write_json(
        tmp_path / "source.json", read_example("source.json") | {"contract_version": version}
    )
    assert load_source(source).contract_version == version
    provenance = read_example("provenance.json") | {"contract_version": version}
    assert load_provenance(write_json(tmp_path / "provenance.json", provenance))


@pytest.mark.parametrize("version", ["0.6.0", "0.8.0", "1.7.0"])
@pytest.mark.parametrize(
    "name, loader", [("source.json", load_source), ("provenance.json", load_provenance)]
)
def test_other_minor_is_refused(tmp_path, name, loader, version):
    path = write_json(tmp_path / name, read_example(name) | {"contract_version": version})
    with pytest.raises(
        ValueError,
        match=rf"{name}: contract_version is {re.escape(version)}; this gridmeta reads 0\.7\.x",
    ):
        loader(path)


def pipeline_with(**changes) -> dict:
    pipeline = read_example("source.json")["pipeline"]
    return {"pipeline": pipeline | changes}


def tools_with(**changes) -> dict:
    tools = read_example("source.json")["pipeline"]["tools"]
    return pipeline_with(tools=tools | changes)


@pytest.mark.parametrize(
    "change, field",
    [
        (pipeline_with(cim_profiles="0.2.0a1"), "pipeline.cim_profiles"),  # 0.1's field
        (tools_with(**{"cim-graph": ">=0.6"}), "pipeline.tools.cim-graph"),  # not exact
        (tools_with(**{"numpy": "2.1.0"}), "pipeline.tools.numpy"),
        (tools_with(**{"cim-builder": "0.3.0"}), "pipeline.tools.cim-builder"),  # 0.5's tool
    ],
)
def test_invalid_pipeline_is_rejected(tmp_path, change, field):
    path = write_json(tmp_path / "source.json", read_example("source.json") | change)
    with pytest.raises(ValueError, match=rf"source\.json: {re.escape(field)}"):
        load_source(path)


@pytest.mark.parametrize(
    "name, field, loader",
    [
        ("source.json", "model_scope", load_source),
        ("source.json", "distribution_area", load_source),
        ("source.json", "feeder_area", load_source),
        ("source.json", "pipeline.tools", load_source),
        ("verify.json", "exported_from", load_verify),
    ],
)
def test_missing_required_field_is_rejected(tmp_path, name, field, loader):
    data = read_example(name)
    *parents, last = field.split(".")
    parent = data
    for key in parents:
        parent = parent[key]
    del parent[last]
    path = write_json(tmp_path / name, data)
    with pytest.raises(ValueError, match=rf"{name}: {re.escape(field)}: Field required"):
        loader(path)


@pytest.mark.parametrize(
    "boundary_feeders, message",
    [
        ({}, r"boundary_feeders: Dictionary should have at least 1 item"),
        ({"cn_head": "vt-0a1b2c3d4e"}, r"boundary_feeders\.cn_head: must be a model_id"),
        ({"cn_head": "VT-0a1b2c3d4"}, r"boundary_feeders\.cn_head: must be a model_id"),
        ({"cn_head": {"model_id": "VT-0a1b2c3d4e"}}, r"boundary_feeders\.cn_head\.str: Input"),
        (
            {"cn_head": {"node": "cn_head", "model_id": "VT-0a1b2c3d4e"}},
            r"boundary_feeders\.cn_head: must be a model_id",
        ),
    ],
)
def test_invalid_boundary_feeders_is_rejected(tmp_path, boundary_feeders, message):
    change = {"boundary_feeders": boundary_feeders}
    path = write_json(tmp_path / "source.json", read_example("source.json") | change)
    with pytest.raises(ValueError, match=rf"source\.json: {message}"):
        load_source(path)


def test_area_frames_is_refused(tmp_path):
    """0.7.0 replaces area_frames with boundary_feeders (contract 3.1)."""
    change = {"area_frames": ["VT-0a1b2c3d4e", "VT-5e6f7a8b9c"]}
    path = write_json(tmp_path / "source.json", read_example("source.json") | change)
    with pytest.raises(ValueError, match=r"source\.json: area_frames: Extra inputs"):
        load_source(path)


def test_own_feeder_must_be_mapped():
    source = load_source(CONTRACT_DIR / "source.json")
    check_own_feeder(CONTRACT_DIR / "source.json", source, "VT-0a1b2c3d4e")
    with pytest.raises(
        ValueError,
        match=r"source\.json: boundary_feeders: no boundary node maps to the package's model_id "
        r"VT-9999999999",
    ):
        check_own_feeder(CONTRACT_DIR / "source.json", source, "VT-9999999999")


@pytest.mark.parametrize("tool", ["cimhub-opendss", "cim-tables"])
def test_missing_tool_is_rejected(tmp_path, tool):
    source = read_example("source.json")
    del source["pipeline"]["tools"][tool]
    path = write_json(tmp_path / "source.json", source)
    with pytest.raises(ValueError, match=rf"source\.json: pipeline\.tools\.{re.escape(tool)}"):
        load_source(path)
