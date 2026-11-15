"""Interface A loaders and models."""

import json
from pathlib import Path

import pytest
import yaml

from generate import GK_SCHEMA, PACKAGE_SCHEMA
from gridmeta.package import load_provenance, load_sanitize, load_source, load_verify

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
    assert source.pipeline.cim_profiles == "0.2.0a1"
    provenance = load_provenance(CONTRACT_DIR / "provenance.json")
    assert provenance.components.DistributionTransformers.inferred == 330
    assert provenance.components.Secondary.missing
    assert load_verify(CONTRACT_DIR / "verify.json").status == "PASS"


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
        ({"contract_version": "0.2.0"}, "contract_version"),
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


def test_unknown_key_is_rejected(tmp_path):
    path = write_json(tmp_path / "verify.json", read_example("verify.json") | {"vpu_min": 0.9})
    with pytest.raises(ValueError, match=r"verify\.json.*vpu_min"):
        load_verify(path)


@pytest.mark.parametrize("version", ["0.1.0", "0.1.9"])
def test_same_major_minor_is_accepted(tmp_path, version):
    source = write_json(
        tmp_path / "source.json", read_example("source.json") | {"contract_version": version}
    )
    assert load_source(source).contract_version == version
    provenance = read_example("provenance.json") | {"contract_version": version}
    assert load_provenance(write_json(tmp_path / "provenance.json", provenance))


@pytest.mark.parametrize(
    "name, loader", [("source.json", load_source), ("provenance.json", load_provenance)]
)
def test_other_minor_is_refused(tmp_path, name, loader):
    path = write_json(tmp_path / name, read_example(name) | {"contract_version": "0.2.0"})
    with pytest.raises(
        ValueError, match=rf"{name}: contract_version is 0\.2\.0; this gridmeta reads 0\.1\.x"
    ):
        loader(path)
