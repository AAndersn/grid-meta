"""Read the JSON files of a feeder package (Grid Kitchen publishing contract, interface A).

Each loader validates one file against the generated models in package_models.py, applies the
rules a schema cannot express, and raises ValueError naming the file and field.
"""

import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from gridmeta.package_models import Provenance, Sanitize, Source, Verify

CONTRACT_VERSION = "0.1.2"
APPLICATION_SPECIFIC = "ApplicationSpecific"

Model = TypeVar("Model", bound=BaseModel)


def read_json(path: Path) -> dict:
    """The JSON content of a package file; a missing or malformed file raises ValueError."""
    if not path.is_file():
        raise ValueError(f"{path}: file is missing")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise ValueError(f"{path}: not valid JSON: {error}") from error


def _validate(path: Path, model: type[Model]) -> Model:
    """One line per problem, each naming the file and the field."""
    path = Path(path)
    try:
        return model.model_validate(read_json(path))
    except ValidationError as error:
        problems = [
            f"{path}: {'.'.join(str(part) for part in problem['loc'])}: {problem['msg']}"
            for problem in error.errors()
        ]
        raise ValueError("\n".join(problems)) from error


def _major_minor(version: str) -> tuple[str, str]:
    major, minor, _patch = version.split(".")
    return major, minor


def _check_contract_version(path: Path, contract_version: str) -> None:
    """Any version with this gridmeta's MAJOR.MINOR is read (contract 3.1)."""
    if _major_minor(contract_version) != _major_minor(CONTRACT_VERSION):
        major, minor = _major_minor(CONTRACT_VERSION)
        raise ValueError(
            f"{path}: contract_version is {contract_version}; this gridmeta reads "
            f"{major}.{minor}.x"
        )


def load_source(path: Path) -> Source:
    """source.json (3.1). `applications` is non-empty exactly when the use case is
    ApplicationSpecific."""
    source = _validate(path, Source)
    _check_contract_version(path, source.contract_version)
    if (source.use_case == APPLICATION_SPECIFIC) != bool(source.applications):
        raise ValueError(
            f"{path}: applications must be non-empty exactly when use_case is "
            f"{APPLICATION_SPECIFIC}; got use_case {source.use_case} and "
            f"applications {source.applications}"
        )
    return source


def load_provenance(path: Path) -> Provenance:
    """provenance.json (3.2). No component has more inferred objects than objects."""
    provenance = _validate(path, Provenance)
    _check_contract_version(path, provenance.contract_version)
    for name, component in provenance.components:
        if component.inferred > component.objects:
            raise ValueError(
                f"{path}: components.{name}.inferred ({component.inferred}) exceeds "
                f"objects ({component.objects})"
            )
    return provenance


def load_verify(path: Path) -> Verify:
    """verify.json (3.3). The publisher, not this loader, applies the PASS and voltage gates."""
    return _validate(path, Verify)


def load_sanitize(path: Path) -> Sanitize:
    """sanitize.json (3.4), present only in a sanitised package."""
    return _validate(path, Sanitize)
