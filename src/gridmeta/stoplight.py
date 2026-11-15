"""The per-component provenance stoplight: provenance.json -> dqv:hasQualityMeasurement
(contract 4.4).

The stoplight describes what is shipped. In a sanitised package (sanitize.json) the components
whose values grid-reducer perturbs, and the coordinates of a layout pass, are Inferred with value
0. A data file without positions makes Coordinates Missing.
"""

from gridmeta.package_models import Provenance, Sanitize
from gridmeta.rounding import round_share

SOURCED_THRESHOLD = 0.80
NO_NOISE = "none"
NOISE_COMPONENTS = {
    "transformers": "DistributionTransformers",
    "lines": "Conductors",
    "loads": "Loads",
    "layout": "Coordinates",
}
COORDINATES = "Coordinates"


def _measurement(component: str, level: str, value: float | None, comment: str) -> dict:
    measurement = {
        "@type": "dqv:QualityMeasurement",
        "dqv:isMeasurementOf": "gk:Metric.SourcedShare",
        "gk:component": f"gk:Component.{component}",
        "gk:provenanceLevel": f"gk:ProvenanceLevel.{level}",
    }
    if value is not None:
        measurement["dqv:value"] = value
    if comment:
        measurement["rdfs:comment"] = comment
    return measurement


def _source_level(objects: int, inferred: int, missing: bool) -> tuple[str, float | None]:
    if missing:
        return "Missing", None
    if objects == 0:
        return "NotPresent", None
    value = round_share(objects - inferred, objects)
    # The threshold applies to dqv:value, which is the rounded share.
    return ("Sourced" if value >= SOURCED_THRESHOLD else "Inferred"), value


def _append(comment: str, text: str) -> str:
    return f"{comment}; {text}" if comment else text


def quality_measurements(
    provenance: Provenance, sanitize: Sanitize | None, has_positions: bool
) -> list[dict]:
    """One measurement per component, in the order of the gk:Component scheme."""
    noise = {}
    if sanitize is not None:
        for category, component in NOISE_COMPONENTS.items():
            level = getattr(sanitize.noise, category)
            if level != NO_NOISE:
                noise[component] = level
    measurements = []
    for component, entry in provenance.components:
        level, value = _source_level(entry.objects, entry.inferred, entry.missing)
        comment = "; ".join(entry.notes)
        # contract 4.5a: the sanitising rules skip Missing and NotPresent components.
        perturbed = level in ("Sourced", "Inferred")
        if (
            perturbed
            and component == COORDINATES
            and sanitize is not None
            and sanitize.layout.enabled
        ):
            level, value = "Inferred", 0.0
            comment = (
                f"coordinates replaced by a force-directed layout ({sanitize.layout.obfuscation})"
            )
        if perturbed and component in noise:
            level, value = "Inferred", 0.0
            comment = _append(comment, f"differential privacy noise ({noise[component]})")
        if component == COORDINATES and not has_positions:
            # contract 4.5a: no dqv:value, and the reason is added to the comment.
            level, value = "Missing", None
            comment = _append(comment, "the shipped data file has no positions")
        measurements.append(_measurement(component, level, value, comment))
    return measurements
