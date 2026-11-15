datamodel-codegen --input src/gridmeta/schemas/DehydrationMetadataV1.schema.json --output src/gridmeta/models.py --base-class pydantic.BaseModel --use-schema-description --use-title-as-name
# The gk vocabulary (context, Turtle, vocabulary.json, record JSON Schema and models) and the
# feeder package models, from src/gridmeta/schemas/gk.linkml.yaml and package.linkml.yaml.
python codegen/generate.py
