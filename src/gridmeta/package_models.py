from __future__ import annotations

import re
import sys
from datetime import (
    date,
    datetime,
    time
)
from decimal import Decimal
from enum import Enum
from typing import (
    Any,
    ClassVar,
    Literal,
    Optional,
    Union
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer
)


metamodel_version = "1.11.0"
version = "0.1.0"


class ConfiguredBaseModel(BaseModel):
    model_config = ConfigDict(
        serialize_by_alias = True,
        validate_by_name = True,
        validate_assignment = True,
        validate_default = True,
        extra = "forbid",
        arbitrary_types_allowed = True,
        use_enum_values = True,
        strict = False,
    )





class LinkMLMeta(RootModel):
    root: dict[str, Any] = {}
    model_config = ConfigDict(frozen=True)

    def __getattr__(self, key:str):
        return getattr(self.root, key)

    def __getitem__(self, key:str):
        return self.root[key]

    def __setitem__(self, key:str, value):
        self.root[key] = value

    def __contains__(self, key:str) -> bool:
        return key in self.root


linkml_meta = LinkMLMeta({'default_prefix': 'gkpkg',
     'default_range': 'string',
     'description': 'The JSON files of one feeder package, written by a pipeline '
                    'and read by gridmeta and the publisher (Grid Kitchen '
                    'publishing contract, interface A, section 3). Regenerate the '
                    'JSON Schema and pydantic models with codegen.sh and never '
                    'edit them by hand.',
     'id': 'https://gridkitchen.pnnl.gov/ns/gk/package',
     'imports': ['linkml:types'],
     'license': 'BSD-3-Clause',
     'name': 'feeder_package',
     'prefixes': {'gkpkg': {'prefix_prefix': 'gkpkg',
                            'prefix_reference': 'https://gridkitchen.pnnl.gov/ns/gk/package#'},
                  'linkml': {'prefix_prefix': 'linkml',
                             'prefix_reference': 'https://w3id.org/linkml/'}},
     'source_file': '/home/ande188/grid-meta/src/gridmeta/schemas/package.linkml.yaml',
     'title': 'Grid Kitchen feeder package'} )

class ModelClass(str, Enum):
    Geographic = "Geographic"
    Generic = "Generic"


class UseCase(str, Enum):
    Representative = "Representative"
    ApplicationSpecific = "ApplicationSpecific"


class Application(str, Enum):
    Protection = "Protection"
    VoltageManagement = "VoltageManagement"
    DERManagement = "DERManagement"
    LoadManagement = "LoadManagement"


class VerifyStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


class PrivacyLevel(str, Enum):
    """
    grid-reducer PrivacyLevel.
    """
    none = "none"
    low = "low"
    moderate = "moderate"
    high = "high"



class Source(ConfiguredBaseModel):
    """
    source.json, the facts the pipeline knows about the source (3.1). Never shipped.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://gridkitchen.pnnl.gov/ns/gk/package', 'tree_root': True})

    contract_version: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Source', 'Provenance']} })
    utility: Utility = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Source']} })
    substation: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Source']} })
    feeder: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Source']} })
    state: str = Field(default=..., description="""USPS code of the state of the feeder head.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Source']} })
    source_export_date: date = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Source']} })
    model_class: ModelClass = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Source']} })
    use_case: UseCase = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Source']} })
    applications: list[Application] = Field(default=..., description="""The applications of an ApplicationSpecific model; empty otherwise.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Source']} })
    multi_feeder_compatible: bool = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Source']} })
    model_scope: str = Field(default=..., description="""The scope in which the utility's source keys are unique, as the .cimtbl master states it in Model = (contract 2).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Source']} })
    pipeline: Pipeline = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Source']} })
    forbidden_strings: list[str] = Field(default=..., description="""Every real name that must not appear in a shipped file.""", min_length=1, json_schema_extra = { "linkml_meta": {'domain_of': ['Source']} })

    @field_validator('contract_version')
    def pattern_contract_version(cls, v):
        pattern=re.compile(r"^\d+\.\d+\.\d+$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid contract_version format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid contract_version format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('state')
    def pattern_state(cls, v):
        pattern=re.compile(r"^[A-Z]{2}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid state format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid state format: {v}"
            raise ValueError(err_msg)
        return v


class Utility(ConfiguredBaseModel):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://gridkitchen.pnnl.gov/ns/gk/package'})

    name: str = Field(default=..., description="""Used only for the model id and the name scan; never published.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Utility', 'Pipeline']} })


class Pipeline(ConfiguredBaseModel):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://gridkitchen.pnnl.gov/ns/gk/package'})

    name: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Utility', 'Pipeline']} })
    commit: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Pipeline']} })
    run: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Pipeline']} })
    tools: Tools = Field(default=..., description="""The exact installed versions of the packages the shipped notebook uses.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Pipeline']} })

    @field_validator('commit')
    def pattern_commit(cls, v):
        pattern=re.compile(r"^[0-9a-f]{40}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid commit format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid commit format: {v}"
            raise ValueError(err_msg)
        return v


class Tools(ConfiguredBaseModel):
    """
    The exact installed version (importlib.metadata.version) of each package the shipped notebook pins, keyed by PyPI distribution name (contract 3).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://gridkitchen.pnnl.gov/ns/gk/package'})

    cim_profiles: str = Field(default=..., alias="cim-profiles", json_schema_extra = { "linkml_meta": {'domain_of': ['Tools']} })
    cim_graph: str = Field(default=..., alias="cim-graph", json_schema_extra = { "linkml_meta": {'domain_of': ['Tools']} })
    cim_tables: str = Field(default=..., alias="cim-tables", json_schema_extra = { "linkml_meta": {'domain_of': ['Tools']} })
    cimhub_opendss: str = Field(default=..., alias="cimhub-opendss", json_schema_extra = { "linkml_meta": {'domain_of': ['Tools']} })
    opendssdirect_py: str = Field(default=..., alias="opendssdirect.py", json_schema_extra = { "linkml_meta": {'domain_of': ['Tools']} })

    @field_validator('cim_profiles')
    def pattern_cim_profiles(cls, v):
        pattern=re.compile(r"^\d[0-9A-Za-z.+!-]*$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid cim_profiles format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid cim_profiles format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('cim_graph')
    def pattern_cim_graph(cls, v):
        pattern=re.compile(r"^\d[0-9A-Za-z.+!-]*$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid cim_graph format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid cim_graph format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('cim_tables')
    def pattern_cim_tables(cls, v):
        pattern=re.compile(r"^\d[0-9A-Za-z.+!-]*$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid cim_tables format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid cim_tables format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('cimhub_opendss')
    def pattern_cimhub_opendss(cls, v):
        pattern=re.compile(r"^\d[0-9A-Za-z.+!-]*$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid cimhub_opendss format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid cimhub_opendss format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('opendssdirect_py')
    def pattern_opendssdirect_py(cls, v):
        pattern=re.compile(r"^\d[0-9A-Za-z.+!-]*$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid opendssdirect_py format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid opendssdirect_py format: {v}"
            raise ValueError(err_msg)
        return v


class Provenance(ConfiguredBaseModel):
    """
    provenance.json, per-component source and inferred counts (3.2).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://gridkitchen.pnnl.gov/ns/gk/package'})

    contract_version: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Source', 'Provenance']} })
    components: Components = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Provenance']} })

    @field_validator('contract_version')
    def pattern_contract_version(cls, v):
        pattern=re.compile(r"^\d+\.\d+\.\d+$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid contract_version format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid contract_version format: {v}"
            raise ValueError(err_msg)
        return v


class Components(ConfiguredBaseModel):
    """
    One entry for every component, including the absent ones. The names are those of the gk Component enumeration (checked by tests/test_package.py).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://gridkitchen.pnnl.gov/ns/gk/package'})

    Topology: ComponentProvenance = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Components']} })
    Conductors: ComponentProvenance = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Components']} })
    DistributionTransformers: ComponentProvenance = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Components']} })
    SubstationSource: ComponentProvenance = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Components']} })
    Loads: ComponentProvenance = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Components']} })
    DER: ComponentProvenance = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Components']} })
    Protection: ComponentProvenance = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Components']} })
    VoltageControl: ComponentProvenance = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Components']} })
    Secondary: ComponentProvenance = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Components']} })
    Coordinates: ComponentProvenance = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Components']} })
    TimeSeries: ComponentProvenance = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Components']} })


class ComponentProvenance(ConfiguredBaseModel):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://gridkitchen.pnnl.gov/ns/gk/package'})

    objects: int = Field(default=..., description="""Number of model objects of the component.""", ge=0, json_schema_extra = { "linkml_meta": {'domain_of': ['ComponentProvenance']} })
    inferred: int = Field(default=..., description="""How many of the objects have a key parameter not taken from the source data.""", ge=0, json_schema_extra = { "linkml_meta": {'domain_of': ['ComponentProvenance']} })
    missing: bool = Field(default=..., description="""The component exists in the real feeder, but the source has no data for it.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ComponentProvenance']} })
    notes: list[str] = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ComponentProvenance']} })


class Verify(ConfiguredBaseModel):
    """
    verify.json, the power-flow result (3.3).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://gridkitchen.pnnl.gov/ns/gk/package'})

    status: VerifyStatus = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Verify']} })
    converged: bool = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Verify']} })
    solver: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Verify']} })
    exported_from: str = Field(default=..., description="""The data file the solved deck was exported from; the publisher requires <model_id>.jsonld.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Verify']} })
    solved_at: datetime  = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Verify']} })
    min_vpu: float = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Verify']} })
    max_vpu: float = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Verify']} })
    total_load_kw: float = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Verify']} })
    isolated_buses: int = Field(default=..., ge=0, json_schema_extra = { "linkml_meta": {'domain_of': ['Verify']} })
    high_leg_nodes: Optional[int] = Field(default=0, description="""Nodes whose per-unit voltage is taken against the high-leg base of a four-wire delta secondary rather than the bus base (contract 3.3). Absent means 0.""", ge=0, json_schema_extra = { "linkml_meta": {'domain_of': ['Verify'], 'ifabsent': 'int(0)'} })
    ungrounded_nodes: Optional[int] = Field(default=0, description="""Buses of an ungrounded secondary network, whose voltage is read line to line against the winding's ratedU (contract 3.3). Absent means 0.""", ge=0, json_schema_extra = { "linkml_meta": {'domain_of': ['Verify'], 'ifabsent': 'int(0)'} })


class Sanitize(ConfiguredBaseModel):
    """
    sanitize.json, the summary of a grid-reducer sanitise run (3.4).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://gridkitchen.pnnl.gov/ns/gk/package'})

    tool: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Sanitize']} })
    version: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Sanitize']} })
    config_sha256: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Sanitize']} })
    reduce: ReduceSettings = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Sanitize']} })
    layout: LayoutSettings = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Sanitize', 'NoiseSettings']} })
    noise: NoiseSettings = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Sanitize']} })
    rename: bool = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Sanitize']} })

    @field_validator('config_sha256')
    def pattern_config_sha256(cls, v):
        pattern=re.compile(r"^[0-9a-f]{64}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid config_sha256 format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid config_sha256 format: {v}"
            raise ValueError(err_msg)
        return v


class ReduceSettings(ConfiguredBaseModel):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://gridkitchen.pnnl.gov/ns/gk/package'})

    transformers: bool = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ReduceSettings', 'NoiseSettings']} })
    lines: bool = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ReduceSettings', 'NoiseSettings']} })


class LayoutSettings(ConfiguredBaseModel):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://gridkitchen.pnnl.gov/ns/gk/package'})

    enabled: bool = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['LayoutSettings']} })
    obfuscation: PrivacyLevel = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['LayoutSettings']} })


class NoiseSettings(ConfiguredBaseModel):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://gridkitchen.pnnl.gov/ns/gk/package'})

    transformers: PrivacyLevel = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ReduceSettings', 'NoiseSettings']} })
    lines: PrivacyLevel = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ReduceSettings', 'NoiseSettings']} })
    loads: PrivacyLevel = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['NoiseSettings']} })
    layout: PrivacyLevel = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Sanitize', 'NoiseSettings']} })


# Model rebuild
# see https://pydantic-docs.helpmanual.io/usage/models/#rebuilding-a-model
Source.model_rebuild()
Utility.model_rebuild()
Pipeline.model_rebuild()
Tools.model_rebuild()
Provenance.model_rebuild()
Components.model_rebuild()
ComponentProvenance.model_rebuild()
Verify.model_rebuild()
Sanitize.model_rebuild()
ReduceSettings.model_rebuild()
LayoutSettings.model_rebuild()
NoiseSettings.model_rebuild()
