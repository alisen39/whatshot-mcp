# OpenAPI

`whatshot-backend-v1.json` is the generated OpenAPI 3.1 HTTP surface for
`/api/v1`. It references the generated JSON Schemas and freezes method, path,
query parameter, request body, response, error, and authentication boundaries.

The canonical document is shared by two Backend deployment policies. Standard
OpenAPI `security` therefore declares Bearer as optional. The
`x-whatshot-deployment-auth` extension makes the deployment rule explicit:

- Core data endpoints are public.
- Cloud data endpoints require Bearer authentication and enforce each
  operation's `x-whatshot-required-scopes` values.
- `/capabilities` remains public so an MCP can negotiate a deployment-level
  catalog before serving clients.

Do not interpret optional Bearer as permission for a Cloud implementation to
accept anonymous data requests; the Cloud deployment policy is normative.

Do not edit the JSON file directly. Change the Pydantic models or exporter,
regenerate, and run the artifact drift test.
