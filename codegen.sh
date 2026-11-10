datamodel-codegen --input src/gridmeta/schemas/DehydrationMetadataV1.schema.json --output src/gridmeta/models.py --base-class pydantic.BaseModel --use-schema-description --use-title-as-name
gen-json-schema src/gridmeta/schemas/noise_catalog.linkml.yaml > src/gridmeta/schemas/NoiseCatalog.schema.json
gen-pydantic src/gridmeta/schemas/noise_catalog.linkml.yaml > src/gridmeta/noise_catalog_models.py
