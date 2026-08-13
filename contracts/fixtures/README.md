# Contract fixtures

Fixtures are storage-independent HTTP payload examples. Contract tests load
them through the public Pydantic models. Local DuckDB and Cloud PostgreSQL test
adapters should seed equivalent logical data and compare normalized complete
responses, excluding only documented values such as request IDs and opaque
cursor bytes.

The `v1/` directory also contains language-neutral conformance vectors for
canonical `boardKey` construction and search-text normalization. Every Backend
implementation must run the same vectors; implementations must not maintain a
separate set of identity or normalization rules.
