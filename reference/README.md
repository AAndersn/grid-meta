# Reference datasets

`gridmeta describe --reference-dir DIR` (or `GRIDMETA_REFERENCE_DIR`) reads the datasets below
to derive `gk:setting`, `gk:settingShares`, `gk:regionClass` and `gk:climateRegion` from a
package's `private/service_points.csv` (publishing contract 4.5). The files in this directory of
the repository are templates. The real directory is `gridpantry/datasets/reference`, kept with
DVC. Every lookup runs locally: no coordinate is sent to any web service.

## Setting up the directory

1. Copy `SOURCES.toml` and this README into `gridpantry/datasets/reference`.
2. Download each file from its `url` into that directory and check that the `vintage` is the
   one on the source page. Change `file`, `url` and `vintage` together if a newer vintage is
   used.
3. Fill in `sha256` with the output of `sha256sum <file>`.
4. `dvc add` the directory and commit the `.dvc` file in gridpantry.

gridmeta stops with an error naming `SOURCES.toml` and the field if a table or key is missing,
a file is missing, or a SHA-256 does not match. Changing a file without changing its SHA-256
is therefore impossible by accident.

## Datasets

| Table | Content | Format gridmeta reads |
|---|---|---|
| `nces_locale` | NCES EDGE locale boundaries | zipped shapefile in longitude/latitude (`.prj` starting `GEOGCS`); field `LOCALE`, the 2-digit locale code (11 to 43) |
| `counties` | Census cartographic boundary counties | zipped shapefile in longitude/latitude; field `GEOID`, the 5-digit county FIPS code |
| `cbsa` | Census CBSA delineation (list 1) | the Census `.xlsx` as published; a header row with `FIPS State Code`, `FIPS County Code` and `Metropolitan/Micropolitan Statistical Area`. A county not listed is `Outside` |
| `climate_regions` | DOE Building America climate region by county | CSV, see below |

A projected shapefile is refused; reproject it to longitude/latitude first and record that in
`vintage`.

### The Building America table

There is no machine-readable source, so a person builds it once from the DOE/PNNL guide to
Building America climate regions by county. The source document still has to be chosen by the
project lead; put its URL in `url` and its edition in `vintage`.

`building_america_climate_regions.csv` has exactly two columns:

```
county_fips,climate_region
50001,Cold
```

- `county_fips`: the 5-digit county FIPS code, with leading zeros, as in the Census `GEOID`.
- `climate_region`: one of `HotHumid`, `HotDry`, `MixedHumid`, `MixedDry`, `Cold`, `VeryCold`,
  `Subarctic`, `Marine` (the `gk:ClimateRegion` values).

Every county that holds the customer-weighted majority of some feeder must be in the table;
otherwise `describe` stops and names the county.
