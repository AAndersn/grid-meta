"""Load and check the noise catalog (schemas/noise_catalog.linkml.yaml)."""

import json
from collections import Counter
from pathlib import Path

import jsonschema
import yaml

from gridmeta.noise_catalog_models import NoiseCatalog

PACKAGE_DIR = Path(__file__).parent
DEFAULT_CATALOG = PACKAGE_DIR / "noise_catalog.yaml"
CATALOG_SCHEMA = PACKAGE_DIR / "schemas" / "NoiseCatalog.schema.json"


def load_noise_catalog(path: Path = DEFAULT_CATALOG) -> NoiseCatalog:
    """Validate a catalog (YAML or JSON) against the schema and return it.

    Raises on a schema violation, a target listed twice, or a rule naming a mode the catalog does
    not define.
    """
    data = yaml.safe_load(Path(path).read_text())
    jsonschema.validate(data, json.loads(CATALOG_SCHEMA.read_text()))
    catalog = NoiseCatalog.model_validate(data)

    repeated = [target for target, n in Counter(r.target for r in catalog.rules).items() if n > 1]
    if repeated:
        raise ValueError(f"{path}: targets listed more than once: {repeated}")
    mode_names = {mode.name for mode in catalog.modes}
    for rule in catalog.rules:
        unknown = set(rule.modes) - mode_names
        if unknown:
            raise ValueError(f"{path}: {rule.target} names undefined modes {sorted(unknown)}")
    return catalog
