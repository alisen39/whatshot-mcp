# JSON Schema

`v1/` contains generated JSON Schema for every public request, success envelope,
and error envelope in Contract v1. The Pydantic models are authoritative. CI
fails when generated schemas differ from committed artifacts.
