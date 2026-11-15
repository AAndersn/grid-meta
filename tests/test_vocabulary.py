"""The gk vocabulary: the generated files are current and match the contract examples."""

import json
import re
from pathlib import Path

import jsonschema
import pytest
import yaml
from rdflib import RDF, SKOS, XSD, Graph, Literal, URIRef

from generate import GK_SCHEMA, generated_files
from gridmeta.record_models import FeederRecord
from gridmeta.vocabulary import (
    CONTEXT_FILE,
    TURTLE_FILE,
    VOCABULARY_FILE,
    VOCABULARY_VERSION,
    inline_context,
    record_json_schema,
)

CONTRACT_DIR = Path(__file__).parent / "data" / "contract"
GK = "https://gridkitchen.pnnl.gov/ns/gk#"

# Contract 4.2 and 4.3.
RECORD_PROPERTIES = [
    "gk:modelClass",
    "gk:useCase",
    "gk:application",
    "gk:state",
    "gk:regionClass",
    "gk:setting",
    "gk:settingShares",
    "gk:climateRegion",
    "gk:primaryVoltage",
    "gk:voltageClass",
    "gk:hvConnection",
    "gk:mvConnection",
    "gk:lvConnection",
    "gk:feederLength",
    "gk:undergroundShare",
    "gk:loadCount",
    "gk:customerCount",
    "gk:loadSizeDistribution",
    "gk:dgCount",
    "gk:dgCapacityAC",
    "gk:dgSizeDistribution",
    "gk:evCount",
    "gk:fuseCount",
    "gk:recloserCount",
    "gk:sectionalizerCount",
    "gk:substationLTC",
    "gk:regulatorCount",
    "gk:capacitorCount",
    "gk:secondaryModeling",
    "gk:lowVoltageNetwork",
    "gk:geographicSpecificity",
    "gk:multiFeederCompatible",
    "dqv:hasQualityMeasurement",
    "gk:vocabularyVersion",
]
# Contract 4.2: set by the publisher, so in the vocabulary but not in the feeder record.
PUBLISHER_PROPERTIES = ["gk:siblingGroup", "gk:contentHash"]
# Contract decision 10.1 and 13.10.
DROPPED_TERMS = [
    "utilityType",
    "UtilityType",
    "serviceTerritory",
    "region",
    "statcomCount",
    "siblingFeeder",
]
ENUMERATIONS = {
    "ModelClass": ["Geographic", "Generic"],
    "UseCase": ["Representative", "ApplicationSpecific"],
    "Application": ["Protection", "VoltageManagement", "DERManagement", "LoadManagement"],
    "RegionClass": ["Metropolitan", "Micropolitan", "Outside"],
    "Setting": ["Urban", "Suburban", "Rural", "DeepRural"],
    "ClimateRegion": [
        "HotHumid",
        "HotDry",
        "MixedHumid",
        "MixedDry",
        "Cold",
        "VeryCold",
        "Subarctic",
        "Marine",
    ],
    "Connection": [
        "Delta",
        "Wye",
        "WyeGrounded",
        "CenterTap",
        "OpenDelta",
        "OpenWye",
        "Zigzag",
        "SinglePhase",
    ],
    "SecondaryModeling": ["None", "AggregateLoad", "IndividualCustomers"],
    "GeographicSpecificity": ["LatLong", "XY", "None"],
    "ProvenanceLevel": ["Sourced", "Inferred", "Missing", "NotPresent"],
    "Component": [
        "Topology",
        "Conductors",
        "DistributionTransformers",
        "SubstationSource",
        "Loads",
        "DER",
        "Protection",
        "VoltageControl",
        "Secondary",
        "Coordinates",
        "TimeSeries",
    ],
}
# Properties whose component is "—" in contract 4.2.
NO_COMPONENT = {
    "gk:modelClass",
    "gk:useCase",
    "gk:application",
    "gk:state",
    "gk:regionClass",
    "gk:setting",
    "gk:settingShares",
    "gk:climateRegion",
    "gk:vocabularyVersion",
    *PUBLISHER_PROPERTIES,
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


@pytest.fixture(scope="module")
def vocabulary() -> dict:
    return read_json(VOCABULARY_FILE)


@pytest.fixture(scope="module")
def turtle_graph() -> Graph:
    return Graph().parse(TURTLE_FILE, format="turtle")


def test_generated_files_are_current():
    stale = [
        str(path) for path, content in generated_files().items() if path.read_text() != content
    ]
    assert not stale, f"run python codegen/generate.py; stale: {stale}"


def test_context_equals_contract_example():
    assert CONTEXT_FILE.read_bytes() == (CONTRACT_DIR / "gk-context.jsonld").read_bytes()


def test_version_is_the_schema_version():
    schema = yaml.safe_load(GK_SCHEMA.read_text())
    assert VOCABULARY_VERSION == schema["version"] == "0.1.0"
    assert schema["slots"]["vocabularyVersion"]["equals_string"] == VOCABULARY_VERSION


def test_record_schema_covers_contract_properties():
    properties = record_json_schema()["properties"]
    assert set(properties) == set(RECORD_PROPERTIES) | {"@context"}


def test_enumerations_match_contract(vocabulary):
    for name, values in ENUMERATIONS.items():
        scheme = vocabulary["enumerations"][f"gk:{name}"]
        assert scheme["values"] == [f"gk:{name}.{value}" for value in values]


def test_vocabulary_lists_component_of_every_property(vocabulary):
    for key in RECORD_PROPERTIES + PUBLISHER_PROPERTIES:
        if not key.startswith("gk:"):
            continue
        entry = vocabulary["properties"][key]
        assert entry["label"] and entry["description"]
        if key in NO_COMPONENT:
            assert entry["component"] is None, key
        else:
            assert entry["component"] in vocabulary["enumerations"]["gk:Component"]["values"], key


def test_every_property_has_label_description_unit_and_component(vocabulary):
    for key, entry in vocabulary["properties"].items():
        assert {"label", "description", "unit", "component"} <= set(entry), key
        assert entry["label"] and entry["description"], key


def test_publisher_properties_are_terms_but_not_record_fields(vocabulary):
    record_properties = record_json_schema()["properties"]
    for key in PUBLISHER_PROPERTIES:
        assert key in vocabulary["properties"]
        assert inline_context()[key] == {"@type": "xsd:string"}
        assert key not in record_properties


def test_dropped_terms_are_absent():
    for path in [CONTEXT_FILE, TURTLE_FILE, VOCABULARY_FILE, GK_SCHEMA]:
        text = path.read_text()
        for term in DROPPED_TERMS:
            assert not re.search(rf"gk[:#]{term}\b", text), (path, term)
    schema = yaml.safe_load(GK_SCHEMA.read_text())
    assert not set(DROPPED_TERMS) & (set(schema["slots"]) | set(schema["enums"]))


def test_catalog_metric_definition_is_the_vocabulary_description(vocabulary):
    """The catalog's Metric definition is copied from vocabulary.json (contract 13.3)."""
    catalog = read_json(CONTRACT_DIR / "catalog.jsonld")
    description = vocabulary["values"]["gk:Metric.SourcedShare"]["description"]
    for dataset in catalog["dataset"]:
        for measurement in dataset["hasQualityMeasurement"]:
            assert measurement["isMeasurementOf"]["definition"] == description


def test_vocabulary_values_have_labels(vocabulary):
    for scheme_id, scheme in vocabulary["enumerations"].items():
        for value_id in scheme["values"]:
            value = vocabulary["values"][value_id]
            assert value["label"] and value["description"]
            assert value["scheme"] == scheme_id


def test_quantities_have_units(vocabulary):
    units = {key: entry.get("unit") for key, entry in vocabulary["properties"].items()}
    assert units["gk:primaryVoltage"] == units["gk:voltageClass"] == "kV"
    assert units["gk:feederLength"] == "km"
    assert units["gk:dgCapacityAC"] == "kVA"
    assert units["gk:loadSizeDistribution"] == "kW"
    assert units["gk:dgSizeDistribution"] == "kVA"
    assert units["gk:undergroundShare"] == units["gk:share"] == "1"


def test_turtle_concepts_are_in_their_schemes(turtle_graph, vocabulary):
    for scheme_id, scheme in vocabulary["enumerations"].items():
        scheme_iri = URIRef(GK + scheme_id.removeprefix("gk:"))
        assert (scheme_iri, RDF.type, SKOS.ConceptScheme) in turtle_graph
        for value_id in scheme["values"]:
            concept = URIRef(GK + value_id.removeprefix("gk:"))
            assert (concept, RDF.type, SKOS.Concept) in turtle_graph
            assert (concept, SKOS.inScheme, scheme_iri) in turtle_graph
            label = vocabulary["values"][value_id]["label"]
            assert (concept, SKOS.prefLabel, Literal(label, lang="en")) in turtle_graph


def test_turtle_quantities_have_qudt_units(turtle_graph):
    has_unit = URIRef("http://qudt.org/schema/qudt/hasUnit")
    kilovolt = URIRef("http://qudt.org/vocab/unit/KiloV")
    assert (URIRef(GK + "primaryVoltage"), has_unit, kilovolt) in turtle_graph


def test_example_record_validates_and_round_trips():
    record = read_json(CONTRACT_DIR / "record.json")
    jsonschema.Draft202012Validator(record_json_schema()).validate(record)
    model = FeederRecord.model_validate(record)
    assert model.model_dump(mode="json", by_alias=True, exclude_none=True) == record


@pytest.mark.parametrize(
    "change",
    [
        {"gk:annualPeakLoad": 0},  # an excluded metric (contract 4.2)
        {"gk:setting": "gk:Setting.Rural "},
        {"gk:voltageClass": 12.47},
        {"gk:undergroundShare": 9},  # a percentage, not a share
        {"gk:vocabularyVersion": "0.0.9"},
    ],
)
def test_invalid_record_is_rejected(change):
    record = read_json(CONTRACT_DIR / "record.json") | change
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(record, record_json_schema())


def test_example_record_expands_with_inline_context():
    """Every gk: value expands to an IRI or a literal of its declared type (contract section 11)."""
    context = inline_context()
    record = read_json(CONTRACT_DIR / "record.json") | {"@context": context}
    graph = Graph().parse(data=json.dumps(record), format="json-ld")
    checked = set()
    for _, predicate, value in graph:
        key = str(predicate).replace(GK, "gk:")
        declared = context.get(key, {}).get("@type")
        if declared == "@id":
            assert isinstance(value, URIRef), (key, value)
        elif declared is not None:
            assert value.datatype == XSD[declared.removeprefix("xsd:")], (key, value)
        checked.add(key)
    assert {"gk:setting", "gk:primaryVoltage", "gk:share", "gk:loadCount"} <= checked
