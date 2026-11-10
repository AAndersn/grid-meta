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


metamodel_version = "None"
version = "1.0.0"


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

    @model_serializer(mode='wrap', when_used='unless-none')
    def treat_empty_lists_as_none(
            self, handler: SerializerFunctionWrapHandler,
            info: SerializationInfo) -> dict[str, Any]:
        if info.exclude_none:
            _instance = self.model_copy()
            for field, field_info in type(_instance).model_fields.items():
                if getattr(_instance, field) == [] and not(
                        field_info.is_required()):
                    setattr(_instance, field, None)
        else:
            _instance = self
        return handler(_instance, info)



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


linkml_meta = LinkMLMeta({'default_prefix': 'gridmeta',
     'default_range': 'string',
     'description': 'Which properties of a dehydrated feeder model receive '
                    'differential-privacy noise, by which mechanism and with which '
                    'sensitivity. The privacy mode (low, moderate, high) supplies '
                    'epsilon and delta; a rule supplies the mechanism and '
                    'sensitivity. See PNNL-37723, "Differential Privacy in Grid '
                    'Kitchen", sections 2.2 and 2.3.',
     'id': 'https://w3id.org/grid-kitchen/gridmeta/noise-catalog',
     'imports': ['linkml:types'],
     'license': 'BSD-3-Clause',
     'name': 'noise_catalog',
     'prefixes': {'gridmeta': {'prefix_prefix': 'gridmeta',
                               'prefix_reference': 'https://w3id.org/grid-kitchen/gridmeta/'},
                  'linkml': {'prefix_prefix': 'linkml',
                             'prefix_reference': 'https://w3id.org/linkml/'}},
     'source_file': 'src/gridmeta/schemas/noise_catalog.linkml.yaml',
     'title': 'Grid Kitchen Noise Catalog'} )

class Mechanism(str, Enum):
    gaussian = "gaussian"
    """
    Continuous values: sigma = sensitivity * sqrt(2 ln(1.25 / delta)) / epsilon.
    """
    discrete_laplace = "discrete_laplace"
    """
    Integer values; geometric noise with p = exp(-epsilon / sensitivity).
    """
    randomized_response = "randomized_response"
    """
    Booleans; the reported value is flipped with a probability set by epsilon.
    """
    none = "none"
    """
    Published unchanged (categorical or low-variability properties).
    """


class SensitivityKind(str, Enum):
    absolute = "absolute"
    """
    The rule's sensitivity, in the property's own units.
    """
    range_over_n = "range_over_n"
    """
    sensitivity * (global max - global min) / n, over the whole dataset; n is the number of items in it.
    """
    range_over_sqrt_n = "range_over_sqrt_n"
    """
    sensitivity * (global max - global min) / sqrt(n), over the whole dataset.
    """



class NoiseCatalog(ConfiguredBaseModel):
    """
    The privacy modes and one noise rule per catalogued property.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/grid-kitchen/gridmeta/noise-catalog',
         'tree_root': True})

    modes: list[PrivacyMode] = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['NoiseCatalog', 'NoiseRule']} })
    rules: list[NoiseRule] = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['NoiseCatalog']} })


class PrivacyMode(ConfiguredBaseModel):
    """
    A named privacy level; smaller epsilon and delta give stronger privacy and more noise.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/grid-kitchen/gridmeta/noise-catalog'})

    name: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['PrivacyMode']} })
    epsilon: float = Field(default=..., description="""Privacy budget.""", ge=0, json_schema_extra = { "linkml_meta": {'domain_of': ['PrivacyMode']} })
    delta: float = Field(default=..., description="""Probability of failing the epsilon guarantee (Gaussian mechanism only).""", ge=0, json_schema_extra = { "linkml_meta": {'domain_of': ['PrivacyMode']} })


class NoiseRule(ConfiguredBaseModel):
    """
    How one property is perturbed.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/grid-kitchen/gridmeta/noise-catalog',
         'rules': [{'description': 'Noise-adding mechanisms need a sensitivity.',
                    'postconditions': {'slot_conditions': {'sensitivity': {'name': 'sensitivity',
                                                                           'required': True}}},
                    'preconditions': {'slot_conditions': {'mechanism': {'any_of': [{'equals_string': 'gaussian'},
                                                                                   {'equals_string': 'discrete_laplace'}],
                                                                        'name': 'mechanism'}}}}]})

    target: str = Field(default=..., description="""<component>.<property>, e.g. transformers.kva.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NoiseRule']} })
    mechanism: Mechanism = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['NoiseRule']} })
    sensitivity: Optional[float] = Field(default=None, description="""In the property's own units when sensitivity_kind is absolute; otherwise a multiplier on the range term (1 for the catalog's plain (max - min) / n).""", ge=0, json_schema_extra = { "linkml_meta": {'domain_of': ['NoiseRule']} })
    sensitivity_kind: Optional[SensitivityKind] = Field(default='absolute', json_schema_extra = { "linkml_meta": {'domain_of': ['NoiseRule'], 'ifabsent': 'SensitivityKind(absolute)'} })
    min_value: Optional[float] = Field(default=None, description="""Smallest plausible value; noisy values are clipped to it.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NoiseRule']} })
    max_value: Optional[float] = Field(default=None, description="""Largest plausible value; noisy values are clipped to it. Absent means unbounded.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NoiseRule']} })
    modes: Optional[list[str]] = Field(default=[], description="""The modes that apply this rule; absent means every mode.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NoiseCatalog', 'NoiseRule']} })
    note: Optional[str] = Field(default=None, description="""Why this mechanism and sensitivity were chosen.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NoiseRule']} })

    @field_validator('target')
    def pattern_target(cls, v):
        pattern=re.compile(r"^[a-z_]+\.[a-z_]+$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid target format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid target format: {v}"
            raise ValueError(err_msg)
        return v


# Model rebuild
# see https://pydantic-docs.helpmanual.io/usage/models/#rebuilding-a-model
NoiseCatalog.model_rebuild()
PrivacyMode.model_rebuild()
NoiseRule.model_rebuild()
