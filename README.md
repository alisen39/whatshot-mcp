# WhatsHot MCP

`whatshot-mcp` is the single open-source MCP server for WhatsHot. It connects
to either a local WhatsHot Backend or the hosted WhatsHot Backend through the
same versioned HTTP contract.

This repository contains the Contract v1 models and the MCP implementation.
The MCP server only talks to a versioned WhatsHot Backend over
HTTP; it never opens DuckDB or PostgreSQL itself.

The project is licensed under the MIT License and owned by `alisen39`.

## Requirements

- Python 3.12 or newer
- One standard installation; no optional dependency extras are currently
  defined

The supported installation form is `python -m pip install whatshot-mcp`. No
`[all]` or other extras are defined.

For local development:

```bash
python -m pip install -e .
pytest
python -m build
```

## Run

Copy `config.example.toml`, then start the primary Streamable HTTP transport:

```bash
whatshot-mcp serve --config ./config.toml
```

Clients connect to `http://127.0.0.1:6691/mcp` by default. Streamable HTTP is
the only supported transport.

The HTTP process also exposes a minimal public `GET /health` probe and a
deployment-level `GET /ready` probe. In hosted Bearer passthrough mode,
`/ready` requires a syntactically valid WhatsHot Developer API key while
`/health` remains public.

Operational commands:

```bash
whatshot-mcp config validate --config ./config.toml
whatshot-mcp backend check --config ./config.toml
whatshot-mcp version
```

`backend check` validates the capabilities envelope, Contract v1 and
`boardKeyVersion`. Its exit codes are `0` success, `2` invalid configuration,
`3` Backend unavailable, `4` invalid/error Contract response and `5`
incompatible board-key version.

Hosted deployments use one end-user credential across both HTTP boundaries.
Each client sends its own WhatsHot Developer API key:

```http
Authorization: Bearer wh_live_...
```

The MCP validates the credential format, binds it only to the current request,
and sends the same key to the Cloud Backend Contract as a Bearer credential.
The Cloud Backend remains authoritative for key status, expiry, scopes,
resources, rate limits, and usage attribution. Concurrent requests do not share
credentials, and the key is never exposed as a tool argument, result, or log
field. Supabase login JWTs and the removed shared MCP token format are rejected
by the hosted MCP boundary.

For loopback development and operational `backend check`, a static Backend key
may still be stored in an uncommitted local configuration or resolved from
`backend.api_key_env`. `server.auth.mode="bearer_passthrough"` deliberately
forbids that static key so hosted requests cannot silently fall back to a
deployment identity.

When a TLS reverse proxy preserves the public Host header, add that exact host
to `server.allowed_hosts` so SDK DNS-rebinding protection accepts both the
public hostname and the automatically retained loopback hosts:

```toml
[server]
allowed_hosts = ["mcp.whatshot.top"]
allowed_origins = []
```

Example remote client configuration:

```json
{
  "mcp": {
    "whatshot": {
      "type": "remote",
      "url": "https://mcp.whatshot.top/mcp",
      "enabled": true,
      "headers": {
        "Authorization": "Bearer {env:WHATSHOT_API_KEY}"
      }
    }
  }
}
```

Supported environment overrides include:

```text
WHATSHOT_MCP_SERVER_BIND
WHATSHOT_MCP_SERVER_PORT
WHATSHOT_MCP_SERVER_PATH
WHATSHOT_MCP_SERVER_AUTH_MODE
WHATSHOT_MCP_BACKEND_URL
WHATSHOT_MCP_BACKEND_API_KEY
WHATSHOT_MCP_BACKEND_TIMEOUT_SECONDS
WHATSHOT_MCP_BACKEND_CAPABILITIES_TTL_SECONDS
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

Keyword matching: a word matches when an item's title or description contains
it — Chinese by characters, other scripts by whole words (`GPT` matches
`ChatGPT`, `AI` does not match `said`). The Cloud Backend answers
`history/search` from its search index: one evidence record per hot-list item
per day (`observedAt`/`firstSeenAt` = first listing that day, `lastSeenAt` =
last listing, `rank` = best rank, `captureId` = null) and one per newsflash,
for the last 90 days; `coverage.limitations` states this. Since 0.4.0 the hot
event analysis takes its last-seen time from `lastSeenAt`. Use
`whatshot_get_trend_series` for every capture of one item.

At startup the MCP validates and freezes one deployment-level capabilities
snapshot. It registers only tools whose required Backend capability is enabled;
changing Backend features requires restarting the MCP. User permissions never
change `tools/list`: they are enforced by the Backend on each call, so every
user of one deployment sees the same publicly cacheable catalog.

## Contract v1

The source of truth is the Pydantic model package at
`src/whatshot_mcp/contracts/v1/`.

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
key may be kept in the ignored local copy or supplied by environment variable
only for loopback development and operational checks. Unauthenticated
Streamable HTTP is restricted to loopback. A non-loopback bind requires
`server.auth.mode = "bearer_passthrough"`; every request then supplies its own
`wh_live_` key, and configuring a static Backend key fails closed. A
non-loopback bind must also declare `server.allowed_hosts`; reverse-proxied
loopback deployments declare the preserved public Host as shown above. `oauth`
is reserved and currently fails closed.

## License

MIT License. See `LICENSE`.

## Release

PyPI publishing uses GitHub Actions Trusted Publishing; the repository does not
store a long-lived PyPI token. After validation and a SemVer version update,
push the matching `v<version>` tag. The dedicated `publish.yml` workflow builds
the wheel and source distribution, then publishes them from the protected
`pypi` environment.
