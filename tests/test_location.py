"""M2: location-derived properties (contract 4.5), against synthetic polygons."""

import tomllib
from pathlib import Path

import pytest

from gridmeta.location import DATASETS, load_reference, location_properties, read_polygons
from gridmeta.testing import (
    PROJECTED_PRJ,
    write_reference_dir,
    EXAMPLE_SERVICE_POINTS,
    square,
    write_reference,
    write_shapefile_zip,
)

# Urban (12) and Suburban (21) side by side; two counties, one micropolitan.
LOCALES = [(square(-101, 40), "12"), (square(-100, 40), "21"), (square(-99, 40), "43")]
COUNTIES = [(square(-101, 40), "99001"), (square(-100, 40, 2), "99003")]
CBSA = {"99003": "Micropolitan Statistical Area"}
CLIMATE = {"99001": "HotHumid", "99003": "MixedDry"}


def describe_points(tmp_path, rows: list[str], reference_dir=None) -> dict:
    if reference_dir is None:
        reference_dir = write_reference(tmp_path / "reference", LOCALES, COUNTIES, CBSA, CLIMATE)
    service_points = tmp_path / "service_points.csv"
    service_points.write_text("\n".join(["load_mrid,lat,lon,customers", *rows]) + "\n")
    return location_properties(service_points, load_reference(reference_dir))


def test_example_shares(tmp_path):
    reference = load_reference(write_reference_dir(tmp_path / "reference"))
    service_points = tmp_path / "service_points.csv"
    service_points.write_text(EXAMPLE_SERVICE_POINTS)
    assert location_properties(service_points, reference) == {
        "gk:setting": "gk:Setting.Rural",
        "gk:settingShares": [
            {"gk:setting": "gk:Setting.Rural", "gk:share": 0.71},
            {"gk:setting": "gk:Setting.DeepRural", "gk:share": 0.29},
        ],
        "gk:regionClass": "gk:RegionClass.Metropolitan",
        "gk:climateRegion": "gk:ClimateRegion.Cold",
    }


def test_weights_are_customers_not_points(tmp_path):
    rows = ["a,40.5,-100.5,1", "b,40.6,-100.5,1", "c,40.5,-100.4,1", "d,40.5,-99.5,10"]
    record = describe_points(tmp_path, rows)
    assert record["gk:setting"] == "gk:Setting.Suburban"
    assert record["gk:settingShares"] == [
        {"gk:setting": "gk:Setting.Urban", "gk:share": 0.23},
        {"gk:setting": "gk:Setting.Suburban", "gk:share": 0.77},
    ]


def test_setting_tie_goes_to_the_earlier_setting(tmp_path):
    record = describe_points(tmp_path, ["a,40.5,-99.5,5", "b,40.5,-100.5,5"])
    assert record["gk:setting"] == "gk:Setting.Urban"


def test_shares_are_in_scheme_order_and_zero_shares_are_omitted(tmp_path):
    record = describe_points(tmp_path, ["a,40.5,-99.5,2", "b,40.5,-100.5,1", "c,40.5,-98.5,0"])
    assert record["gk:settingShares"] == [
        {"gk:setting": "gk:Setting.Urban", "gk:share": 0.33},
        {"gk:setting": "gk:Setting.Suburban", "gk:share": 0.67},
    ]


def test_region_and_climate_follow_the_majority_county(tmp_path):
    record = describe_points(tmp_path, ["a,40.5,-100.5,3", "b,40.5,-99.5,2"])
    assert record["gk:regionClass"] == "gk:RegionClass.Outside"
    assert record["gk:climateRegion"] == "gk:ClimateRegion.HotHumid"
    record = describe_points(tmp_path, ["a,40.5,-100.5,1", "b,40.5,-99.5,4"])
    assert record["gk:regionClass"] == "gk:RegionClass.Micropolitan"
    assert record["gk:climateRegion"] == "gk:ClimateRegion.MixedDry"


def test_county_tie_goes_to_the_smaller_code(tmp_path):
    record = describe_points(tmp_path, ["a,40.5,-99.5,2", "b,40.5,-100.5,2"])
    assert record["gk:climateRegion"] == "gk:ClimateRegion.HotHumid"


def test_point_outside_every_polygon_names_the_load(tmp_path):
    with pytest.raises(ValueError, match=r"service_points\.csv: load far-away is outside"):
        describe_points(tmp_path, ["a,40.5,-100.5,1", "far-away,10.0,10.0,1"])


@pytest.mark.parametrize(
    "rows, message",
    [
        ([], "has no service points"),
        (["a,40.5,-100.5,0"], "customers add up to 0"),
        (["a,40.5,-100.5,1", "a,40.6,-100.5,1"], "load_mrid repeated: a"),
        (["a,95.0,-100.5,1"], "line 2 .load a.: lat or lon is out of range"),
        (["a,40.5,-100.5,many"], "line 2 .load a."),
        (["a,40.5,-100.5,-1"], "customers is negative"),
    ],
)
def test_invalid_service_points(tmp_path, rows, message):
    with pytest.raises(ValueError, match=message):
        describe_points(tmp_path, rows)


def test_wrong_columns(tmp_path):
    service_points = tmp_path / "service_points.csv"
    service_points.write_text("mrid,lat,lon\nx,1,2\n")
    reference = load_reference(write_reference_dir(tmp_path / "reference"))
    with pytest.raises(ValueError, match="the columns must be load_mrid,lat,lon,customers"):
        location_properties(service_points, reference)


def test_checksum_mismatch_names_the_dataset(tmp_path):
    reference_dir = write_reference_dir(tmp_path / "reference")
    (reference_dir / "climate.csv").write_text("county_fips,climate_region\n99001,Marine\n")
    with pytest.raises(ValueError, match=r"SOURCES\.toml: climate_regions\.sha256 is "):
        load_reference(reference_dir)


def test_missing_table_and_empty_field(tmp_path):
    reference_dir = write_reference_dir(tmp_path / "reference")
    sources = reference_dir / "SOURCES.toml"
    text = sources.read_text()
    sources.write_text(text.replace('vintage = "test"', 'vintage = ""', 1))
    with pytest.raises(ValueError, match=r"SOURCES\.toml: nces_locale\.vintage is empty"):
        load_reference(reference_dir)
    sources.write_text(text.replace("[cbsa]", "[cbsa_old]"))
    with pytest.raises(ValueError, match=r"SOURCES\.toml: table \[cbsa\] is missing"):
        load_reference(reference_dir)


def test_county_without_climate_region(tmp_path):
    reference_dir = write_reference(
        tmp_path / "reference", LOCALES, COUNTIES, CBSA, {"99001": "HotHumid"}
    )
    with pytest.raises(ValueError, match=r"climate\.csv: no climate region for county 99003"):
        describe_points(tmp_path, ["a,40.5,-99.5,1"], reference_dir)


def test_unknown_climate_region(tmp_path):
    reference_dir = write_reference(
        tmp_path / "reference", LOCALES, COUNTIES, CBSA, {"99001": "Tropical"}
    )
    with pytest.raises(ValueError, match=r"climate\.csv: line 2: unknown climate_region"):
        load_reference(reference_dir)


def test_projected_shapefile_is_refused(tmp_path):
    path = write_shapefile_zip(tmp_path / "locales.zip", "LOCALE", LOCALES, prj=PROJECTED_PRJ)
    with pytest.raises(ValueError, match="projected"):
        read_polygons(path, "LOCALE")


def test_unknown_locale_code(tmp_path):
    reference_dir = write_reference(
        tmp_path / "reference", [(square(-101, 40, 3), "99")], COUNTIES, CBSA, CLIMATE
    )
    with pytest.raises(ValueError, match="unknown NCES locale code '99'"):
        describe_points(tmp_path, ["a,40.5,-100.5,1"], reference_dir)


def test_sources_template_lists_every_dataset():
    template = tomllib.loads(
        (Path(__file__).parents[1] / "reference" / "SOURCES.toml").read_text()
    )
    assert list(template) == list(DATASETS)
    for entry in template.values():
        assert set(entry) == {"file", "url", "vintage", "sha256"}


def test_testing_reference_dir_loads(tmp_path):
    reference = load_reference(write_reference_dir(tmp_path / "reference"))
    assert reference.region_class == {"99001": "Metropolitan"}
    assert reference.climate_region == {"99001": "Cold"}
