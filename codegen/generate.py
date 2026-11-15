"""Generate every file derived from the LinkML schemas in src/gridmeta/schemas.

From gk.linkml.yaml (the feeder record vocabulary, contract section 4):
  - gk_vocabulary/context.jsonld   the inline JSON-LD context
  - gk_vocabulary/gk.ttl           OWL/RDFS properties plus one SKOS concept scheme per enumeration
  - gk_vocabulary/vocabulary.json  labels, units and components for the portal
  - schemas/FeederRecord.schema.json and record_models.py (pydantic, from that JSON Schema)

LinkML's stock generators key JSON-LD terms and JSON Schema properties by slot name, while the
record's keys are compact IRIs (gk:modelClass), and its OWL generator writes restrictions. So
these files are written here from SchemaView. The record models come from the JSON Schema through
datamodel-codegen, with python field names in snake_case and the compact IRIs as aliases.

From package.linkml.yaml (the feeder package files, contract section 3), whose keys are plain
names, LinkML's stock pydantic generator writes package_models.py.

Run: python codegen/generate.py
"""

import json
import re
import subprocess
import sys
import tempfile
from copy import copy
from pathlib import Path

from linkml.generators.pydanticgen import PydanticGenerator
from linkml_runtime import SchemaView
from linkml_runtime.linkml_model.meta import SlotDefinition
from rdflib import OWL, RDF, RDFS, SKOS, XSD, Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS

REPO_DIR = Path(__file__).resolve().parents[1]
PACKAGE_DIR = REPO_DIR / "src" / "gridmeta"
SCHEMA_DIR = PACKAGE_DIR / "schemas"
GK_SCHEMA = SCHEMA_DIR / "gk.linkml.yaml"
PACKAGE_SCHEMA = SCHEMA_DIR / "package.linkml.yaml"
VOCABULARY_DIR = PACKAGE_DIR / "gk_vocabulary"

QUDT = Namespace("http://qudt.org/schema/qudt/")
DQV = Namespace("http://www.w3.org/ns/dqv#")
LICENSE_IRI = URIRef("https://spdx.org/licenses/BSD-3-Clause.html")

# LinkML type: (JSON Schema, JSON-LD @type, RDF range). Strings and booleans are native JSON-LD
# literals and need no @type.
LITERAL_TYPES = {
    "string": ({"type": "string"}, None, XSD.string),
    "boolean": ({"type": "boolean"}, None, XSD.boolean),
    "integer": ({"type": "integer"}, "xsd:integer", XSD.integer),
    "decimal": ({"type": "number"}, "xsd:decimal", XSD.decimal),
    "uri": ({"type": "string", "format": "uri"}, "@id", None),
    "uriorcurie": ({"type": "string"}, "@id", None),
}


# --- shared helpers --------------------------------------------------------------------------


def top_level_slots(sv: SchemaView) -> list[SlotDefinition]:
    """The schema's own slots, in declaration order, with the default range filled in."""
    slots = []
    for name in sv.schema.slots:
        slot = copy(sv.get_slot(name))
        slot.range = slot.range or sv.schema.default_range
        slots.append(slot)
    return slots


def json_key(sv: SchemaView, slot: SlotDefinition) -> str:
    """The record key of a slot: its compact IRI, or @type for the type designator."""
    if slot.designates_type:
        return "@type"
    return sv.get_uri(slot, expand=False)


def is_gk_term(sv: SchemaView, slot: SlotDefinition) -> bool:
    return not slot.designates_type and json_key(sv, slot).startswith("gk:")


def enum_iri(enum_name: str) -> str:
    return f"gk:{enum_name}"


def value_iri(enum_name: str, value: str) -> str:
    return f"gk:{enum_name}.{value}"


def based_on(sv: SchemaView, slot: SlotDefinition) -> str | None:
    """Compact IRI of the component a property is based on, if any."""
    if "based_on" not in slot.annotations:
        return None
    component = slot.annotations["based_on"].value
    if component not in sv.get_enum("Component").permissible_values:
        raise ValueError(
            f"{GK_SCHEMA}: slot {slot.name} is based on unknown component {component}"
        )
    return value_iri("Component", component)


def range_kind(sv: SchemaView, range_name: str) -> str:
    if range_name in sv.all_enums():
        return "enum"
    if range_name in sv.all_classes():
        return "class"
    if range_name in LITERAL_TYPES:
        return "literal"
    raise ValueError(f"{GK_SCHEMA}: unsupported range {range_name}")


def snake_case(name: str) -> str:
    """modelClass -> model_class, dgCapacityAC -> dg_capacity_ac."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()


def dumps(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


# --- JSON-LD context ---------------------------------------------------------------------------


def context(sv: SchemaView) -> dict:
    """Every schema prefix except linkml, then one term per slot that needs coercion."""
    terms = {
        prefix.prefix_prefix: prefix.prefix_reference
        for prefix in sv.schema.prefixes.values()
        if prefix.prefix_prefix != "linkml"
    }
    for slot in top_level_slots(sv):
        if slot.designates_type:
            continue
        term = {}
        kind = range_kind(sv, slot.range)
        if kind == "enum":
            term["@type"] = "@id"
        elif kind == "literal":
            jsonld_type = LITERAL_TYPES[slot.range][1]
            if "jsonld_type" in slot.annotations:
                jsonld_type = slot.annotations["jsonld_type"].value
            if jsonld_type:
                term["@type"] = jsonld_type
        if slot.multivalued:
            term["@container"] = "@list" if slot.list_elements_ordered else "@set"
        if term:
            terms[json_key(sv, slot)] = term
    return {"@context": terms}


# --- JSON Schema -------------------------------------------------------------------------------


def slot_schema(sv: SchemaView, slot: SlotDefinition, class_uri: str) -> dict:
    if slot.designates_type:
        return {"const": class_uri, "description": slot.description}
    kind = range_kind(sv, slot.range)
    if kind == "literal":
        item = dict(LITERAL_TYPES[slot.range][0])
    else:
        item = {"$ref": f"#/$defs/{slot.range}"}
    if slot.pattern:
        item["pattern"] = slot.pattern
    if slot.minimum_value is not None:
        item["minimum"] = slot.minimum_value
    if slot.maximum_value is not None:
        item["maximum"] = slot.maximum_value
    if slot.equals_string is not None:
        item["const"] = slot.equals_string
    if slot.any_of:
        item["enum"] = [expression.equals_number for expression in slot.any_of]
    if not slot.multivalued:
        return {"description": slot.description, **item}
    array = {"description": slot.description, "type": "array", "items": item}
    if slot.minimum_cardinality is not None:
        array["minItems"] = slot.minimum_cardinality
    if slot.maximum_cardinality is not None:
        array["maxItems"] = slot.maximum_cardinality
    return array


def class_schema(sv: SchemaView, class_name: str) -> dict:
    cls = sv.get_class(class_name)
    class_uri = sv.get_uri(cls, expand=False)
    properties = {}
    required = []
    if cls.tree_root:
        properties["@context"] = {"description": "JSON-LD context; not validated."}
    for slot_name in cls.slots:
        slot = sv.induced_slot(slot_name, class_name)
        key = json_key(sv, slot)
        properties[key] = slot_schema(sv, slot, class_uri)
        if slot.required:
            required.append(key)
    return {
        "title": class_name,
        "description": cls.description,
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def enum_schema(sv: SchemaView, enum_name: str) -> dict:
    enum = sv.get_enum(enum_name)
    values = list(enum.permissible_values)
    return {
        "title": enum_name,
        "description": enum.description,
        "type": "string",
        "enum": [value_iri(enum_name, value) for value in values],
        "x-enum-varnames": values,
    }


def record_json_schema(sv: SchemaView) -> dict:
    """JSON Schema of the feeder record, keyed by compact IRI."""
    root = next(name for name, cls in sv.all_classes().items() if cls.tree_root)
    definitions = {name: class_schema(sv, name) for name in sv.schema.classes if name != root}
    definitions.update({name: enum_schema(sv, name) for name in sv.schema.enums})
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{sv.schema.id}/{sv.schema.version}/FeederRecord.schema.json",
        **class_schema(sv, root),
        "$defs": definitions,
    }


def record_models(json_schema: dict) -> str:
    """Pydantic models of the feeder record, generated from its JSON Schema."""
    aliases = {"@context": "context", "@type": "type"}
    for definition in [json_schema, *json_schema["$defs"].values()]:
        for key in definition.get("properties", {}):
            if ":" in key:
                aliases[key] = snake_case(key.split(":", 1)[1])
    # The CLI, because datamodel-codegen 0.31's generate() recurses without end on this schema.
    with tempfile.TemporaryDirectory() as tmp:
        schema_path = Path(tmp) / "FeederRecord.schema.json"
        aliases_path = Path(tmp) / "aliases.json"
        output = Path(tmp) / "record_models.py"
        schema_path.write_text(dumps(json_schema))
        aliases_path.write_text(dumps(aliases))
        subprocess.run(
            [
                sys.executable,
                "-m",
                "datamodel_code_generator",
                "--input",
                str(schema_path),
                "--input-file-type",
                "jsonschema",
                "--output",
                str(output),
                "--output-model-type",
                "pydantic_v2.BaseModel",
                "--target-python-version",
                "3.11",
                "--aliases",
                str(aliases_path),
                "--allow-population-by-field-name",
                "--disable-timestamp",
                "--field-constraints",
                "--use-annotated",
                "--use-schema-description",
                "--use-field-description",
                "--use-standard-collections",
                "--use-title-as-name",
                "--use-union-operator",
            ],
            check=True,
        )
        return output.read_text()


# --- vocabulary.json ---------------------------------------------------------------------------


def unit_of(slot: SlotDefinition) -> dict:
    if slot.unit is None:
        return {"unit": None, "unitIRI": None}
    return {"unit": slot.unit.symbol, "unitIRI": slot.unit.exact_mappings[0]}


def range_iri(sv: SchemaView, range_name: str) -> str:
    kind = range_kind(sv, range_name)
    if kind == "literal":
        return f"xsd:{range_name}" if range_name != "uri" else "xsd:anyURI"
    return sv.get_uri(range_name, expand=False) if kind == "class" else enum_iri(range_name)


def vocabulary(sv: SchemaView) -> dict:
    """Labels, descriptions, units and components of every gk term (contract 4.1).

    Every property has a unit and a component key; they are null for a property that is not a
    quantity or whose component is "—" in contract 4.2.
    """
    # contract 4.5a: unit and component are null where they don't apply.
    properties = {}
    for slot in top_level_slots(sv):
        if not is_gk_term(sv, slot):
            continue
        properties[json_key(sv, slot)] = {
            "label": slot.title,
            "description": slot.description,
            "range": range_iri(sv, slot.range),
            **unit_of(slot),
            "component": based_on(sv, slot),
        }
    enumerations = {}
    values = {}
    for enum_name, enum in sv.schema.enums.items():
        enumerations[enum_iri(enum_name)] = {
            "label": enum.title,
            "description": enum.description,
            "values": [value_iri(enum_name, value) for value in enum.permissible_values],
        }
        for value, permissible in enum.permissible_values.items():
            values[value_iri(enum_name, value)] = {
                "label": permissible.title,
                "description": permissible.description,
                "scheme": enum_iri(enum_name),
            }
    return {
        "version": sv.schema.version,
        "namespace": sv.schema.prefixes["gk"].prefix_reference,
        "properties": properties,
        "enumerations": enumerations,
        "values": values,
    }


# --- gk.ttl ------------------------------------------------------------------------------------


def turtle(sv: SchemaView) -> str:
    """OWL/RDFS vocabulary with one SKOS concept scheme per enumeration."""
    graph = Graph()
    for prefix in sv.schema.prefixes.values():
        graph.bind(prefix.prefix_prefix, prefix.prefix_reference)
    graph.bind("owl", OWL)
    graph.bind("skos", SKOS)
    graph.bind("qudt", QUDT)
    graph.bind("dct", DCTERMS)
    graph.bind("unit", "http://qudt.org/vocab/unit/")

    def iri(curie: str) -> URIRef:
        return graph.namespace_manager.expand_curie(str(curie))

    def english(text: str) -> Literal:
        return Literal(text, lang="en")

    ontology = URIRef(sv.schema.id)
    graph.add((ontology, RDF.type, OWL.Ontology))
    graph.add((ontology, DCTERMS.title, english(sv.schema.title)))
    graph.add((ontology, DCTERMS.description, english(sv.schema.description)))
    graph.add((ontology, DCTERMS.license, LICENSE_IRI))
    graph.add((ontology, OWL.versionInfo, Literal(sv.schema.version)))

    based_on_property = iri("gk:basedOn")
    graph.add((based_on_property, RDF.type, OWL.AnnotationProperty))
    graph.add((based_on_property, RDFS.label, english("Based on")))
    graph.add(
        (
            based_on_property,
            RDFS.comment,
            english("The component whose provenance light applies to the property."),
        )
    )
    graph.add((based_on_property, RDFS.range, SKOS.Concept))
    graph.add((based_on_property, RDFS.isDefinedBy, ontology))

    for cls in sv.schema.classes.values():
        class_iri = sv.get_uri(cls, expand=False)
        if not class_iri.startswith("gk:"):
            continue
        subject = iri(class_iri)
        graph.add((subject, RDF.type, OWL.Class))
        graph.add((subject, RDFS.label, english(cls.title)))
        graph.add((subject, RDFS.comment, english(cls.description)))
        graph.add((subject, RDFS.isDefinedBy, ontology))

    for slot in top_level_slots(sv):
        if not is_gk_term(sv, slot):
            continue
        subject = iri(json_key(sv, slot))
        kind = range_kind(sv, slot.range)
        if kind == "literal" and LITERAL_TYPES[slot.range][2] is not None:
            graph.add((subject, RDF.type, OWL.DatatypeProperty))
            graph.add((subject, RDFS.range, LITERAL_TYPES[slot.range][2]))
        else:
            graph.add((subject, RDF.type, OWL.ObjectProperty))
        if kind == "enum":
            graph.add((subject, RDFS.range, SKOS.Concept))
        elif kind == "class":
            graph.add((subject, RDFS.range, iri(range_iri(sv, slot.range))))
        graph.add((subject, RDFS.label, english(slot.title)))
        graph.add((subject, RDFS.comment, english(slot.description)))
        graph.add((subject, RDFS.isDefinedBy, ontology))
        if slot.unit is not None:
            graph.add((subject, QUDT.hasUnit, URIRef(slot.unit.exact_mappings[0])))
        component = based_on(sv, slot)
        if component:
            graph.add((subject, based_on_property, iri(component)))

    for enum_name, enum in sv.schema.enums.items():
        scheme = iri(enum_iri(enum_name))
        graph.add((scheme, RDF.type, SKOS.ConceptScheme))
        graph.add((scheme, SKOS.prefLabel, english(enum.title)))
        graph.add((scheme, SKOS.definition, english(enum.description)))
        graph.add((scheme, RDFS.isDefinedBy, ontology))
        for value, permissible in enum.permissible_values.items():
            concept = iri(value_iri(enum_name, value))
            graph.add((concept, RDF.type, SKOS.Concept))
            graph.add((concept, SKOS.inScheme, scheme))
            graph.add((concept, SKOS.topConceptOf, scheme))
            graph.add((concept, SKOS.prefLabel, english(permissible.title)))
            graph.add((concept, SKOS.definition, english(permissible.description)))
            graph.add((concept, SKOS.notation, Literal(value)))
            for predicate, annotation in permissible.annotations.items():
                graph.add((concept, iri(predicate), iri(annotation.value)))

    return graph.serialize(format="turtle")


# --- feeder package (stock LinkML generators) --------------------------------------------------


def package_models() -> str:
    return PydanticGenerator(str(PACKAGE_SCHEMA)).serialize()


# --- entry point -------------------------------------------------------------------------------


def generated_files() -> dict[Path, str]:
    """Every generated file and its content."""
    sv = SchemaView(str(GK_SCHEMA))
    json_schema = record_json_schema(sv)
    return {
        VOCABULARY_DIR / "context.jsonld": dumps(context(sv)),
        VOCABULARY_DIR / "gk.ttl": turtle(sv),
        VOCABULARY_DIR / "vocabulary.json": dumps(vocabulary(sv)),
        SCHEMA_DIR / "FeederRecord.schema.json": dumps(json_schema),
        PACKAGE_DIR / "record_models.py": record_models(json_schema),
        PACKAGE_DIR / "package_models.py": package_models(),
    }


def main() -> None:
    VOCABULARY_DIR.mkdir(exist_ok=True)
    for path, content in generated_files().items():
        path.write_text(content)
        print(f"wrote {path.relative_to(REPO_DIR)}")


if __name__ == "__main__":
    main()
