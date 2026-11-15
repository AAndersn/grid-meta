"""Location-derived feeder record properties (contract 4.5).

Inputs are only the package's private/service_points.csv and the reference datasets that
<reference dir>/SOURCES.toml pins by URL, vintage and SHA-256. Every lookup runs locally; no
coordinate leaves the process, and the record holds only labels.
"""

import csv
import hashlib
import io
import tomllib
import zipfile
from collections import Counter
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import openpyxl
import shapefile
from shapely import STRtree
from shapely.geometry import Point, shape

from gridmeta.rounding import largest_remainder_shares

SOURCES_FILE = "SOURCES.toml"
DATASETS = ("nces_locale", "counties", "cbsa", "climate_regions")
SOURCE_KEYS = ("file", "url", "vintage", "sha256")
SERVICE_POINT_COLUMNS = ["load_mrid", "lat", "lon", "customers"]
SETTING_ORDER = ("Urban", "Suburban", "Rural", "DeepRural")
NCES_SETTINGS = {
    "11": "Urban",
    "12": "Urban",
    "13": "Urban",
    "21": "Suburban",
    "22": "Suburban",
    "23": "Suburban",
    "31": "Rural",
    "32": "Rural",
    "33": "Rural",
    "41": "Rural",
    "42": "DeepRural",
    "43": "DeepRural",
}
NCES_LOCALE_FIELD = "LOCALE"
COUNTY_FIELD = "GEOID"
CBSA_TYPES = {
    "Metropolitan Statistical Area": "Metropolitan",
    "Micropolitan Statistical Area": "Micropolitan",
}
CBSA_COLUMNS = (
    "FIPS State Code",
    "FIPS County Code",
    "Metropolitan/Micropolitan Statistical Area",
)
CLIMATE_COLUMNS = ["county_fips", "climate_region"]
CLIMATE_REGIONS = (
    "HotHumid",
    "HotDry",
    "MixedHumid",
    "MixedDry",
    "Cold",
    "VeryCold",
    "Subarctic",
    "Marine",
)


@dataclass(frozen=True)
class ServicePoint:
    load_mrid: str
    lat: float
    lon: float
    customers: int


@dataclass(frozen=True)
class Polygons:
    """Polygons of one boundary dataset with the label of each, searchable by point."""

    path: Path
    tree: STRtree
    labels: list[str]

    def label_at(self, point: Point) -> list[str]:
        return sorted(
            self.labels[index] for index in self.tree.query(point, predicate="intersects")
        )


@dataclass(frozen=True)
class ReferenceData:
    locales: Polygons
    counties: Polygons
    region_class: dict[str, str]  # county GEOID -> gk:RegionClass name
    climate_region: dict[str, str]  # county GEOID -> gk:ClimateRegion name
    climate_path: Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def source_files(reference_dir: Path) -> dict[str, Path]:
    """Each dataset's file, after its SHA-256 is checked against SOURCES.toml."""
    sources_path = reference_dir / SOURCES_FILE
    if not sources_path.is_file():
        raise ValueError(f"{sources_path}: file is missing")
    sources = tomllib.loads(sources_path.read_text())
    files = {}
    for dataset in DATASETS:
        entry = sources.get(dataset)
        if not isinstance(entry, dict):
            raise ValueError(f"{sources_path}: table [{dataset}] is missing")
        for key in SOURCE_KEYS:
            if not str(entry.get(key, "")).strip():
                raise ValueError(f"{sources_path}: {dataset}.{key} is empty")
        path = reference_dir / entry["file"]
        if not path.is_file():
            raise ValueError(f"{sources_path}: {dataset}.file {path} is missing")
        actual = _sha256(path)
        if actual != entry["sha256"].lower():
            raise ValueError(
                f"{sources_path}: {dataset}.sha256 is {entry['sha256']}, but {path} has {actual}"
            )
        files[dataset] = path
    return files


def read_polygons(path: Path, field: str) -> Polygons:
    """The polygons of a zipped shapefile in geographic coordinates, labelled by one field."""
    with zipfile.ZipFile(path) as archive:
        stems = {
            Path(name).with_suffix("") for name in archive.namelist() if name.endswith(".shp")
        }
        if len(stems) != 1:
            raise ValueError(f"{path}: expected one shapefile, found {len(stems)}")
        stem = stems.pop()
        members = {}
        for suffix in ("shp", "shx", "dbf", "prj"):
            name = f"{stem}.{suffix}"
            if name not in archive.namelist():
                raise ValueError(f"{path}: {name} is missing")
            members[suffix] = archive.read(name)
    if not members["prj"].decode("utf-8", "replace").lstrip().upper().startswith("GEOGCS"):
        raise ValueError(
            f"{path}: the shapefile is projected; it must be in longitude and latitude"
        )
    reader = shapefile.Reader(
        shp=io.BytesIO(members["shp"]),
        shx=io.BytesIO(members["shx"]),
        dbf=io.BytesIO(members["dbf"]),
    )
    if field not in [definition[0] for definition in reader.fields]:
        raise ValueError(f"{path}: the shapefile has no field {field}")
    geometries, labels = [], []
    for record in reader.iterShapeRecords():
        geometries.append(shape(record.shape.__geo_interface__))
        labels.append(str(record.record[field]).strip())
    return Polygons(path, STRtree(geometries), labels)


def _cell(value) -> str:
    return "" if value is None else str(value).strip()


def read_cbsa(path: Path) -> dict[str, str]:
    """County GEOID -> Metropolitan or Micropolitan, from the Census delineation workbook."""
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows = iter(workbook.worksheets[0].iter_rows(values_only=True))
    for row in rows:
        header = [_cell(value) for value in row]
        if all(column in header for column in CBSA_COLUMNS):
            break
    else:
        raise ValueError(f"{path}: no header row with the columns {', '.join(CBSA_COLUMNS)}")
    state_index, county_index, type_index = (header.index(column) for column in CBSA_COLUMNS)
    region_class = {}
    for row in rows:
        state, county = _cell(row[state_index]), _cell(row[county_index])
        if not (state.isdigit() and county.isdigit()):
            continue
        kind = _cell(row[type_index])
        if kind not in CBSA_TYPES:
            raise ValueError(f"{path}: county {state}{county} has the CBSA type {kind!r}")
        region_class[state.zfill(2) + county.zfill(3)] = CBSA_TYPES[kind]
    workbook.close()
    return region_class


def read_climate_regions(path: Path) -> dict[str, str]:
    """County GEOID -> gk:ClimateRegion name, from the Building America table (README)."""
    with path.open(newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames != CLIMATE_COLUMNS:
            raise ValueError(f"{path}: the columns must be {','.join(CLIMATE_COLUMNS)}")
        regions = {}
        for line, row in enumerate(reader, start=2):
            county, region = row["county_fips"].strip(), row["climate_region"].strip()
            if not (len(county) == 5 and county.isdigit()):
                raise ValueError(f"{path}: line {line}: county_fips {county!r} is not 5 digits")
            if region not in CLIMATE_REGIONS:
                raise ValueError(f"{path}: line {line}: unknown climate_region {region!r}")
            regions[county] = region
    return regions


@cache
def load_reference(reference_dir: Path) -> ReferenceData:
    """The reference datasets, read once per process and directory (a batch describes many
    feeders against one directory)."""
    files = source_files(reference_dir)
    return ReferenceData(
        locales=read_polygons(files["nces_locale"], NCES_LOCALE_FIELD),
        counties=read_polygons(files["counties"], COUNTY_FIELD),
        region_class=read_cbsa(files["cbsa"]),
        climate_region=read_climate_regions(files["climate_regions"]),
        climate_path=files["climate_regions"],
    )


def read_service_points(path: Path) -> list[ServicePoint]:
    if not path.is_file():
        raise ValueError(f"{path}: file is missing")
    with path.open(newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames != SERVICE_POINT_COLUMNS:
            raise ValueError(f"{path}: the columns must be {','.join(SERVICE_POINT_COLUMNS)}")
        points = []
        for line, row in enumerate(reader, start=2):
            points.append(_service_point(path, line, row))
    if not points:
        raise ValueError(f"{path}: has no service points")
    duplicates = [
        mrid for mrid, count in Counter(p.load_mrid for p in points).items() if count > 1
    ]
    if duplicates:
        raise ValueError(f"{path}: load_mrid repeated: {', '.join(sorted(duplicates))}")
    if sum(point.customers for point in points) == 0:
        raise ValueError(f"{path}: customers add up to 0")
    return points


def _service_point(path: Path, line: int, row: dict) -> ServicePoint:
    mrid = row["load_mrid"].strip()
    if not mrid:
        raise ValueError(f"{path}: line {line}: load_mrid is empty")
    try:
        lat, lon, customers = float(row["lat"]), float(row["lon"]), int(row["customers"])
    except (TypeError, ValueError) as error:
        raise ValueError(f"{path}: line {line} (load {mrid}): {error}") from error
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f"{path}: line {line} (load {mrid}): lat or lon is out of range")
    if customers < 0:
        raise ValueError(f"{path}: line {line} (load {mrid}): customers is negative")
    return ServicePoint(mrid, lat, lon, customers)


def _label(polygons: Polygons, point: ServicePoint, service_points: Path) -> list[str]:
    labels = polygons.label_at(Point(point.lon, point.lat))
    if not labels:
        raise ValueError(
            f"{service_points}: load {point.load_mrid} is outside every polygon of {polygons.path}"
        )
    return labels


def _setting(polygons: Polygons, point: ServicePoint, service_points: Path) -> str:
    """The setting of a point; on a boundary between locales, the earlier setting."""
    settings = []
    for code in _label(polygons, point, service_points):
        if code not in NCES_SETTINGS:
            raise ValueError(f"{polygons.path}: unknown NCES locale code {code!r}")
        settings.append(NCES_SETTINGS[code])
    return min(settings, key=SETTING_ORDER.index)


def location_properties(service_points_path: Path, reference: ReferenceData) -> dict:
    """gk:setting, gk:settingShares, gk:regionClass and gk:climateRegion, weighted by customers."""
    points = read_service_points(service_points_path)
    by_setting = Counter()
    by_county = Counter()
    for point in points:
        by_setting[_setting(reference.locales, point, service_points_path)] += point.customers
        # On a county boundary the smaller GEOID is taken.
        by_county[_label(reference.counties, point, service_points_path)[0]] += point.customers
    present = [setting for setting in SETTING_ORDER if by_setting[setting] > 0]
    shares = largest_remainder_shares([by_setting[setting] for setting in present])
    # contract 4.5a: a county tie goes to the smaller GEOID.
    county = min(by_county, key=lambda geoid: (-by_county[geoid], geoid))
    if county not in reference.climate_region:
        raise ValueError(f"{reference.climate_path}: no climate region for county {county}")
    majority = max(present, key=lambda s: (by_setting[s], -SETTING_ORDER.index(s)))
    return {
        "gk:setting": f"gk:Setting.{majority}",
        "gk:settingShares": [
            {"gk:setting": f"gk:Setting.{setting}", "gk:share": share}
            for setting, share in zip(present, shares, strict=True)
        ],
        "gk:regionClass": f"gk:RegionClass.{reference.region_class.get(county, 'Outside')}",
        "gk:climateRegion": f"gk:ClimateRegion.{reference.climate_region[county]}",
    }
