"""The generated gk vocabulary files, shipped as package data (contract 4.1 and 6.1).

The files in gk_vocabulary/ are published unchanged at ns/gk/<VOCABULARY_VERSION>/.
"""

import json
from pathlib import Path

PACKAGE_DIR = Path(__file__).parent
VOCABULARY_DIR = PACKAGE_DIR / "gk_vocabulary"
CONTEXT_FILE = VOCABULARY_DIR / "context.jsonld"
TURTLE_FILE = VOCABULARY_DIR / "gk.ttl"
VOCABULARY_FILE = VOCABULARY_DIR / "vocabulary.json"
RECORD_SCHEMA_FILE = PACKAGE_DIR / "schemas" / "FeederRecord.schema.json"

VOCABULARY_VERSION: str = json.loads(VOCABULARY_FILE.read_text())["version"]
CONTEXT_URL = f"https://gridkitchen.pnnl.gov/ns/gk/{VOCABULARY_VERSION}/context.jsonld"


def inline_context() -> dict:
    """The map that goes, inline, in the @context array of every shipped file."""
    return json.loads(CONTEXT_FILE.read_text())["@context"]


def record_json_schema() -> dict:
    return json.loads(RECORD_SCHEMA_FILE.read_text())


def vocabulary() -> dict:
    """vocabulary.json: labels, descriptions, units and components of every term."""
    return json.loads(VOCABULARY_FILE.read_text())
