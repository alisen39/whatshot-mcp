# Contract artifacts

Backend Contract v1 is defined by the strict Pydantic models in
`src/whats_hot_mcp/contracts/v1/`. This directory holds release-facing artifacts
derived from those models.

Rules:

1. Do not hand-maintain a competing field definition here.
2. OpenAPI and JSON Schema artifacts must be generated from the package models
   and checked for a clean diff in CI.
3. Fixtures are stable interoperability examples and must validate against the
   same models in both local and cloud Backend test suites.
4. Breaking changes require a new URL/contract major. Additive optional fields
   remain within the current major.

Backend authentication is a deployment policy, not a capability or a change to
the response envelope. Core implements public data endpoints. Cloud requires a
Bearer token for operations marked with `x-whatshot-required-scopes`, currently
`data:read` for all read endpoints, and may require additional scopes such as
`live:fetch` for live requests. The shared OpenAPI document models Bearer as
optional and records this distinction in `x-whatshot-deployment-auth`.

Regenerate and verify:

```bash
uv run python -m whats_hot_mcp.contracts.export
uv run python -m whats_hot_mcp.contracts.export --check
```

`manifest-v1.json` records SHA-256 checksums for the OpenAPI document and all
JSON Schemas.

Probe a running implementation with the same strict models:

```bash
python -m whats_hot_mcp.contracts.runner \
  --base-url http://127.0.0.1:6690/api/v1
```

For an authenticated Cloud Backend, add `--token-env WHATSHOT_API_TOKEN`.
