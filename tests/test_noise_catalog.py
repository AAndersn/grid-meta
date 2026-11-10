import jsonschema
import pytest
import yaml

from gridmeta.noise_catalog import load_noise_catalog
from gridmeta.noise_catalog_models import Mechanism, SensitivityKind


def test_packaged_catalog_matches_report():
    catalog = load_noise_catalog()
    modes = {mode.name: (mode.epsilon, mode.delta) for mode in catalog.modes}
    assert modes == {"low": (1.0, 1e-5), "moderate": (0.5, 1e-5), "high": (0.1, 1e-12)}

    components = {}
    for rule in catalog.rules:
        component = rule.target.split(".")[0]
        components[component] = components.get(component, 0) + 1
    assert components == {
        "transformers": 14,
        "feeder_sections": 20,
        "capacitors": 5,
        "regulators": 4,
        "switches": 8,
        "substations": 7,
    }


def test_packaged_catalog_rules():
    rules = {rule.target: rule for rule in load_noise_catalog().rules}
    assert rules["transformers.kva"].mechanism == Mechanism.discrete_laplace
    assert rules["feeder_sections.std_ampacity"].sensitivity_kind == (
        SensitivityKind.range_over_sqrt_n
    )
    assert rules["switches.is_normally_open"].mechanism == Mechanism.randomized_response
    assert rules["switches.is_normally_open"].modes == ["high"]
    assert rules["capacitors.install_type"].mechanism == Mechanism.none


def write_catalog(tmp_path, rules):
    path = tmp_path / "catalog.yaml"
    path.write_text(
        yaml.safe_dump({"modes": [{"name": "low", "epsilon": 1.0, "delta": 1e-5}], "rules": rules})
    )
    return path


@pytest.mark.parametrize(
    "rule",
    [
        {"target": "capacitors.kvar", "mechanism": "gaussian"},
        {"target": "Capacitors-kvar", "mechanism": "none"},
        {"target": "switches.kv", "mechanism": "laplace", "sensitivity": 1},
    ],
)
def test_schema_rejects_bad_rules(tmp_path, rule):
    with pytest.raises(jsonschema.ValidationError):
        load_noise_catalog(write_catalog(tmp_path, [rule]))


def test_rejects_repeated_target_and_unknown_mode(tmp_path):
    repeated = [{"target": "switches.kv", "mechanism": "none"}] * 2
    with pytest.raises(ValueError, match="more than once"):
        load_noise_catalog(write_catalog(tmp_path, repeated))
    unknown = [{"target": "switches.kv", "mechanism": "none", "modes": ["high"]}]
    with pytest.raises(ValueError, match="undefined modes"):
        load_noise_catalog(write_catalog(tmp_path, unknown))
