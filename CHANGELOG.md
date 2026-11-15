# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),  
and this project adheres to [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added

* ✨ New features that have been added but not released yet.
* The `gk:` feeder record vocabulary 0.1.0 (Grid Kitchen publishing contract v0.1.1, section 4):
  LinkML source `schemas/gk.linkml.yaml`, and generated from it the JSON-LD context, `gk.ttl`
  (OWL/RDFS plus SKOS concept schemes), `vocabulary.json`, the record JSON Schema and pydantic
  models (`gridmeta.record_models`). Regenerate with `codegen.sh`.
* Feeder package models and loaders for `source.json`, `provenance.json`, `verify.json` and
  `sanitize.json` (`gridmeta.package`).
* `gridmeta.identity.model_id` and `sibling_group`, the keyed feeder and substation identifiers
  (contract section 2).
* `gridmeta describe <package_dir> [-o record.json] [--reference-dir DIR]` and
  `gridmeta.describe.describe(package_dir, reference_dir)`: one feeder package to one feeder
  record. Structural properties from the CIM JSON-LD data file (`gridmeta.structure`, read with
  CIM-Graph `JSONLDFile`), location-derived properties from `private/service_points.csv` and the
  pinned reference datasets (`gridmeta.location`, `reference/`), and the per-component stoplight
  (`gridmeta.stoplight`).

### Changed

* 🔁 Changes in existing functionality.

### Deprecated

* ⚠️ Features soon-to-be removed or replaced.

### Removed

* 🧹 Features that have been removed in this version.

### Fixed

* 🐛 Bug fixes.

### Security

* 🔐 Security patches.

---

## [1.0.0] - 2025-06-02

### Added

* Released a first open source version of GridMeta.
* Supports creating dehydrated metadata from given OpenDSS model.
