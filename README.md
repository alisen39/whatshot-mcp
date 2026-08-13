# WhatsHot MCP

`whats-hot-mcp` is the planned single open-source MCP server for WhatsHot. It
will connect to either a local WhatsHot Backend or the hosted WhatsHot Backend
through the same versioned HTTP contract.

This repository contains the Contract v1 models and the first `core-read` MCP
implementation. The MCP server only talks to a versioned WhatsHot Backend over
HTTP; it never opens DuckDB or PostgreSQL itself.

The project is licensed under the MIT License. The planned GitHub owner is
`alisen39`; the repository and PyPI distribution have not been published yet.

## Requirements

- Python 3.12 or newer
- One standard installation; no optional dependency extras are currently
  defined

Once a release is published, the only supported installation form will be
`python -m pip install whats-hot-mcp`. No `[all]` or other extras are currently
defined.

For local development:

```bash
python -m pip install -e .
pytest
python -m build
```

## Run

Copy `config.example.toml`, then start the primary Streamable HTTP transport:

```bash
whats-hot-mcp serve --config ./config.toml
```

The original `whats-hot-mcp --config ./config.toml` form remains compatible.

Clients connect to `http://127.0.0.1:6691/mcp` by default. A compatibility stdio
transport uses the same fixed Tool Catalog:

```bash
whats-hot-mcp --config ./config.toml --transport stdio
```

The HTTP process also exposes a minimal public `GET /health` probe and a
deployment-level `GET /ready` probe. When static inbound authentication is
enabled, `/ready` requires the same Bearer token while `/health` remains public.

Operational commands:

```bash
whats-hot-mcp config validate --config ./config.toml
whats-hot-mcp backend check --config ./config.toml
whats-hot-mcp version
```

`backend check` validates the capabilities envelope, Contract v1 and
`boardKeyVersion`. Its exit codes are `0` success, `2` invalid configuration,
`3` Backend unavailable, `4` invalid/error Contract response and `5`
incompatible board-key version.

The Backend API key may be stored as `backend.api_key` in the uncommitted local
configuration file, or resolved from `backend.api_key_env`; the environment
value takes precedence. The key is sent only as an `Authorization: Bearer`
request header and is never a tool argument.

There are two independent authentication boundaries:

- MCP client → MCP Server: Streamable HTTP may use the configured inbound
  static Bearer token. The stdio compatibility transport has no HTTP boundary
  and is unchanged.
- MCP Server → Backend `/api/v1`: Core data endpoints are public, while Cloud
  data endpoints require the configured Backend Bearer token and enforce their
  declared scopes. The shared OpenAPI contract marks Bearer as optional and
  records the normative choice in `x-whatshot-deployment-auth`.

An inbound MCP token is never reused as a Backend token, and the Backend API
key is never exposed as a tool argument.
Supported environment overrides include:

```text
WHATS_HOT_MCP_SERVER_BIND
WHATS_HOT_MCP_SERVER_PORT
WHATS_HOT_MCP_SERVER_PATH
WHATS_HOT_MCP_SERVER_AUTH_MODE
WHATS_HOT_MCP_SERVER_TOKEN_ENV
WHATS_HOT_MCP_SERVER_TOKEN
WHATS_HOT_MCP_BACKEND_URL
WHATS_HOT_MCP_BACKEND_API_KEY
WHATS_HOT_MCP_BACKEND_TIMEOUT_SECONDS
WHATS_HOT_MCP_BACKEND_CAPABILITIES_TTL_SECONDS
```

The first fixed Universal Tool Catalog contains:

- `whatshot_get_capabilities`
- `whatshot_list_sources`
- `whatshot_get_source_schema`
- `whatshot_get_current`
- `whatshot_get_current_batch`
- `whatshot_query_history`
- `whatshot_search_history`
- `whatshot_get_trend_series`
- `whatshot_get_data_coverage`
- `whatshot_analyze_hot_event`
- `whatshot_analyze_newsflash_coverage`

When the startup capabilities snapshot reports `navigation=true`, the same
open MCP package additionally registers these Cloud tools:

- `whatshot_list_navigation` — cursor-paged category/site discovery
- `whatshot_fetch_category_hotlists` — bounded current boards for one category

Both tools require the Backend `navigation` capability and `data:read` scope.
They are selected from capabilities, not a Backend-name check. A request with
`freshness=live` is still authorized by the Cloud Backend, which additionally
requires its `live:fetch` scope.

The analysis tools scan `history/search` pages through the same Backend
Contract. `scanBudget` limits evidence examined while `evidenceLimit` separately
limits evidence returned. Responses always report `analysisComplete`,
`scannedCount`, and `coverage`; lifecycle times are explicitly marked
approximate when the scan budget stops pagination. Analysis does not create or
update a research run.

At startup the MCP validates and freezes one deployment-level capabilities
snapshot. It registers only tools whose required Backend capability is enabled;
changing Backend features requires restarting the MCP. User permissions never
change `tools/list`: they are enforced by the Backend on each call, so every
user of one deployment sees the same publicly cacheable catalog.

## Contract v1

The source of truth is the Pydantic model package at
`src/whats_hot_mcp/contracts/v1/`.

- All public JSON fields serialize as `camelCase`.
- All models reject undeclared fields.
- All timestamps require an explicit timezone.
- Successful Backend responses use `{ "data": ..., "meta": ... }`.
- Failed Backend responses use the stable error envelope defined by
  `ErrorEnvelope`.
- `core-read` and `history-read` are distinct capability profiles. A Backend
  may offer current data while history storage is disabled.
- `boardKey` is generated by the documented canonical algorithm and must be
  identical in local and hosted Backends.

The `contracts/` directory describes how OpenAPI, JSON Schema, and fixtures are
published without creating a second hand-maintained contract definition.

## Configuration

`config.example.toml` records the runtime configuration boundary. A real Backend
key may be kept in the ignored local copy or supplied by environment variable.
Unauthenticated Streamable HTTP is restricted to loopback. A non-loopback bind
requires `server.auth.mode = "static_token"` and a non-empty token resolved from
`server.auth.token_env`. The incoming token is used only at the HTTP boundary;
it is never a tool argument or log field. `oauth` is reserved and currently
fails closed.

## License

MIT License. See `LICENSE`.
