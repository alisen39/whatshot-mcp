# Shared Backend contract tests

This directory will become the reusable conformance suite run against both
Backend implementations. Tests must exercise the same request vectors against:

- the Core daemon with a temporary DuckDB and fake Fetch Service;
- the Cloud API with an isolated PostgreSQL/Redis test environment.

The first milestone validates model and fixture conformance only. HTTP transport,
cursor snapshot behavior, error mapping, and complete cross-Backend response
equality are follow-up milestones.

