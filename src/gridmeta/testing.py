"""Synthetic reference datasets for tests of gridmeta and of its users (contract 4.5).

`write_reference_dir(path)` writes square locale and county polygons, a CBSA workbook, a climate
table and a SOURCES.toml pinning them by SHA-256, in the formats gridmeta.location reads.
`EXAMPLE_SERVICE_POINTS` is a service_points.csv whose customers give the location properties of
the contract's examples/record.json. No real boundaries: the county codes use the unused state
code 99.
"""

import hashlib
import zipfile
from pathlib import Path

import openpyxl
import shapefile

GEOGRAPHIC_PRJ = 'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["Degree",0.0174532925199433]]'
PROJECTED_PRJ = 'PROJCS["WGS_1984_Web_Mercator",GEOGCS["GCS_WGS_1984"]]'


def square(west: float, south: float, size: float = 1.0) -> list[list[float]]:
    """A closed ring, clockwise as shapefiles want outer rings."""
    east, north = west + size, south + size
    return [[west, south], [west, north], [east, north], [east, south], [west, south]]


def write_shapefile_zip(
    path: Path, field: str, polygons: list[tuple[list, str]], prj: str = GEOGRAPHIC_PRJ
) -> Path:
    stem = path.with_suffix("")
    with shapefile.Writer(str(stem), shapeType=shapefile.POLYGON) as writer:
        writer.field(field, "C", size=8)
        for ring, label in polygons:
            writer.poly([ring])
            writer.record(label)
    stem.with_suffix(".prj").write_text(prj)
    with zipfile.ZipFile(path, "w") as archive:
        for suffix in (".shp", ".shx", ".dbf", ".prj"):
            archive.write(stem.with_suffix(suffix), stem.name + suffix)
            stem.with_suffix(suffix).unlink()
    return path


def write_cbsa(path: Path, counties: dict[str, str]) -> Path:
    """The Census layout: two title rows, the header, the counties, a footnote."""
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["List 1. CORE BASED STATISTICAL AREAS (CBSAs)"])
    sheet.append([])
    sheet.append(
        [
            "CBSA Code",
            "CBSA Title",
            "Metropolitan/Micropolitan Statistical Area",
            "County/County Equivalent",
            "FIPS State Code",
            "FIPS County Code",
        ]
    )
    for geoid, kind in counties.items():
        sheet.append(["99999", "Example Area", kind, "Example County", geoid[:2], geoid[2:]])
    sheet.append(["Note: synthetic delineation for the tests."])
    workbook.save(path)
    return path


def write_climate(path: Path, regions: dict[str, str]) -> Path:
    lines = ["county_fips,climate_region"] + [
        f"{geoid},{region}" for geoid, region in regions.items()
    ]
    path.write_text("\n".join(lines) + "\n")
    return path


def write_sources(reference_dir: Path, files: dict[str, Path]) -> Path:
    tables = []
    for dataset, path in files.items():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        tables.append(
            f'[{dataset}]\nfile = "{path.name}"\nurl = "https://example.org/{path.name}"\n'
            f'vintage = "test"\nsha256 = "{digest}"\n'
        )
    sources = reference_dir / "SOURCES.toml"
    sources.write_text("\n".join(tables))
    return sources


def write_reference(
    reference_dir: Path,
    locales: list[tuple[list, str]],
    counties: list[tuple[list, str]],
    cbsa: dict[str, str],
    climate: dict[str, str],
) -> Path:
    reference_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "nces_locale": write_shapefile_zip(reference_dir / "locales.zip", "LOCALE", locales),
        "counties": write_shapefile_zip(reference_dir / "counties.zip", "GEOID", counties),
        "cbsa": write_cbsa(reference_dir / "cbsa.xlsx", cbsa),
        "climate_regions": write_climate(reference_dir / "climate.csv", climate),
    }
    write_sources(reference_dir, files)
    return reference_dir


def write_reference_dir(reference_dir: Path) -> Path:
    """Rural (41) west of longitude -100 and Deep rural (42) east of it, in one metropolitan,
    cold county."""
    return write_reference(
        reference_dir,
        locales=[(square(-101, 40), "41"), (square(-100, 40), "42")],
        counties=[(square(-101, 40, 2), "99001")],
        cbsa={"99001": "Metropolitan Statistical Area"},
        climate={"99001": "Cold"},
    )


# 71 customers in the Rural square and 29 in the Deep rural one: Rural 0.71, DeepRural 0.29.
EXAMPLE_SERVICE_POINTS = (
    "load_mrid,lat,lon,customers\n"
    "load-1,40.5,-100.5,70\n"
    "load-2,40.2,-100.8,1\n"
    "load-3,40.5,-99.5,29\n"
)
