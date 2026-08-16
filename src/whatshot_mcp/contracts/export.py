"""Deterministically export Backend Contract v1 release artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from whatshot_mcp.contracts.v1 import (
    BackendCapabilities,
    BatchCurrentData,
    BatchCurrentRequest,
    CategoryCurrentData,
    CategoryCurrentRequest,
    Coverage,
    CoverageQuery,
    CurrentData,
    CurrentRequest,
    ErrorEnvelope,
    HistoryPageData,
    HistoryQuery,
    HistorySearchQuery,
    HotEventAnalysisData,
    HotEventAnalysisQuery,
    NavigationData,
    NavigationQuery,
    NewsflashCoverageAnalysisData,
    NewsflashCoverageAnalysisQuery,
    SourceDetail,
    SourceListData,
    SourceListQuery,
    SuccessEnvelope,
    TrendData,
    TrendQuery,
)

CONTRACT_VERSION = "1"

SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "analysis-hot-event-query": HotEventAnalysisQuery,
    "analysis-hot-event-result": HotEventAnalysisData,
    "analysis-newsflash-coverage-query": NewsflashCoverageAnalysisQuery,
    "analysis-newsflash-coverage-result": NewsflashCoverageAnalysisData,
    "batch-current-request": BatchCurrentRequest,
    "batch-current-response": SuccessEnvelope[BatchCurrentData],
    "category-current-request": CategoryCurrentRequest,
    "category-current-response": SuccessEnvelope[CategoryCurrentData],
    "capabilities-response": SuccessEnvelope[BackendCapabilities],
    "coverage-query": CoverageQuery,
    "coverage-response": SuccessEnvelope[Coverage],
    "current-request": CurrentRequest,
    "current-response": SuccessEnvelope[CurrentData],
    "error-response": ErrorEnvelope,
    "history-query": HistoryQuery,
    "history-response": SuccessEnvelope[HistoryPageData],
    "history-search-query": HistorySearchQuery,
    "navigation-query": NavigationQuery,
    "navigation-response": SuccessEnvelope[NavigationData],
    "source-detail-response": SuccessEnvelope[SourceDetail],
    "source-list-query": SourceListQuery,
    "source-list-response": SuccessEnvelope[SourceListData],
    "trend-query": TrendQuery,
    "trend-response": SuccessEnvelope[TrendData],
}


def _json(value: Any) -> str:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _schema_ref(name: str) -> dict[str, str]:
    return {"$ref": f"../jsonschema/v1/{name}.schema.json"}


def _response(name: str, description: str = "Successful response") -> dict[str, Any]:
    return {
        "description": description,
        "content": {"application/json": {"schema": _schema_ref(name)}},
    }


def _error_responses() -> dict[str, Any]:
    response = _response("error-response", "Stable Backend error response")
    return {
        "400": response,
        "401": response,
        "403": response,
        "404": response,
        "409": response,
        "429": response,
        "500": response,
        "503": response,
    }


def _query_parameter(
    name: str,
    schema: dict[str, Any],
    *,
    required: bool = False,
) -> dict[str, Any]:
    return {
        "name": name,
        "in": "query",
        "required": required,
        "schema": schema,
    }


def _history_parameters(*, keyword: bool = False) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    if keyword:
        values.append(
            _query_parameter(
                "keyword",
                {"type": "string", "minLength": 1, "maxLength": 500},
                required=True,
            )
        )
    values.extend(
        [
            _query_parameter("site", {"type": "string"}),
            _query_parameter("boardKey", {"type": "string"}),
            _query_parameter(
                "kind",
                {"type": "string", "enum": ["hotlist", "newsflash", "gold"]},
            ),
            _query_parameter("since", {"type": "string", "format": "date-time"}),
            _query_parameter("until", {"type": "string", "format": "date-time"}),
            _query_parameter(
                "limit",
                {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
            ),
            _query_parameter("cursor", {"type": "string"}),
        ]
    )
    return values


def build_openapi() -> dict[str, Any]:
    """Return the language-neutral HTTP surface for Backend Contract v1."""

    errors = _error_responses()
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "WhatsHot Backend Contract",
            "version": "1.0.0-rc.1",
        },
        "servers": [{"url": "/api/v1"}],
        "paths": {
            "/capabilities": {
                "get": {
                    "operationId": "getCapabilities",
                    "responses": {"200": _response("capabilities-response"), **errors},
                    "security": [],
                }
            },
            "/sources": {
                "get": {
                    "operationId": "listSources",
                    "parameters": [
                        _query_parameter(
                            "kind",
                            {
                                "type": "string",
                                "enum": ["hotlist", "newsflash", "gold"],
                            },
                        ),
                        _query_parameter("cursor", {"type": "string"}),
                        _query_parameter(
                            "limit",
                            {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 200,
                                "default": 50,
                            },
                        ),
                    ],
                    "responses": {"200": _response("source-list-response"), **errors},
                    "x-whatshot-required-scopes": ["data:read"],
                }
            },
            "/sources/{site}": {
                "get": {
                    "operationId": "getSource",
                    "parameters": [
                        {
                            "name": "site",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": _response("source-detail-response"), **errors},
                    "x-whatshot-required-scopes": ["data:read"],
                }
            },
            "/current": {
                "post": {
                    "operationId": "fetchCurrent",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": _schema_ref("current-request")
                            }
                        },
                    },
                    "responses": {"200": _response("current-response"), **errors},
                    "x-whatshot-required-scopes": ["data:read"],
                }
            },
            "/current/batch": {
                "post": {
                    "operationId": "fetchCurrentBatch",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": _schema_ref("batch-current-request")
                            }
                        },
                    },
                    "responses": {"200": _response("batch-current-response"), **errors},
                    "x-whatshot-required-scopes": ["data:read"],
                }
            },
            "/navigation": {
                "get": {
                    "operationId": "listNavigation",
                    "parameters": [
                        _query_parameter("category", {"type": "string"}),
                        _query_parameter("cursor", {"type": "string"}),
                        _query_parameter(
                            "limit",
                            {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 200,
                                "default": 50,
                            },
                        ),
                    ],
                    "responses": {"200": _response("navigation-response"), **errors},
                    "x-whatshot-required-scopes": ["data:read"],
                }
            },
            "/category/current": {
                "post": {
                    "operationId": "fetchCategoryCurrent",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": _schema_ref("category-current-request")
                            }
                        },
                    },
                    "responses": {
                        "200": _response("category-current-response"),
                        **errors,
                    },
                    "x-whatshot-required-scopes": ["data:read"],
                }
            },
            "/history": {
                "get": {
                    "operationId": "queryHistory",
                    "parameters": _history_parameters(),
                    "responses": {"200": _response("history-response"), **errors},
                    "x-whatshot-required-scopes": ["data:read"],
                }
            },
            "/history/search": {
                "get": {
                    "operationId": "searchHistory",
                    "parameters": _history_parameters(keyword=True),
                    "responses": {"200": _response("history-response"), **errors},
                    "x-whatshot-required-scopes": ["data:read"],
                }
            },
            "/history/trends": {
                "get": {
                    "operationId": "getTrendSeries",
                    "parameters": [
                        _query_parameter("site", {"type": "string"}, required=True),
                        _query_parameter("boardKey", {"type": "string"}, required=True),
                        _query_parameter("itemId", {"type": "string"}, required=True),
                        _query_parameter(
                            "bucket",
                            {
                                "type": "string",
                                "enum": ["10m", "1h", "6h", "1d"],
                                "default": "1h",
                            },
                        ),
                        _query_parameter(
                            "since", {"type": "string", "format": "date-time"}
                        ),
                        _query_parameter(
                            "until", {"type": "string", "format": "date-time"}
                        ),
                    ],
                    "responses": {"200": _response("trend-response"), **errors},
                    "x-whatshot-required-scopes": ["data:read"],
                }
            },
            "/coverage": {
                "get": {
                    "operationId": "getDataCoverage",
                    "parameters": [
                        _query_parameter("site", {"type": "string"}),
                        _query_parameter("boardKey", {"type": "string"}),
                        _query_parameter(
                            "kind",
                            {
                                "type": "string",
                                "enum": ["hotlist", "newsflash", "gold"],
                            },
                        ),
                    ],
                    "responses": {"200": _response("coverage-response"), **errors},
                    "x-whatshot-required-scopes": ["data:read"],
                }
            },
        },
        # One canonical document covers two deployment policies. The empty
        # Security Requirement makes Bearer optional in standard OpenAPI;
        # deployments then enforce the policy declared below.
        "security": [{}, {"bearerAuth": []}],
        "x-whatshot-deployment-auth": {
            "selection": "deployment",
            "appliesTo": "operations with x-whatshot-required-scopes",
            "capabilitiesPublic": True,
            "policies": {
                "core": {
                    "bearerRequired": False,
                    "description": "Core data endpoints are public.",
                },
                "cloud": {
                    "bearerRequired": True,
                    "description": (
                        "Cloud data endpoints require Bearer authentication and "
                        "enforce each operation's declared scopes."
                    ),
                },
            },
        },
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": (
                        "Optional in the shared Contract; required for Cloud data "
                        "endpoints by deployment policy."
                    ),
                }
            }
        },
    }


def build_artifacts() -> dict[Path, str]:
    artifacts: dict[Path, str] = {}
    for name, model in SCHEMA_MODELS.items():
        artifacts[Path("contracts/jsonschema/v1") / f"{name}.schema.json"] = _json(
            model.model_json_schema(by_alias=True, mode="validation")
        )
    artifacts[Path("contracts/openapi/whatshot-backend-v1.json")] = _json(
        build_openapi()
    )

    checksums = {
        str(path): hashlib.sha256(content.encode()).hexdigest()
        for path, content in sorted(artifacts.items(), key=lambda item: str(item[0]))
    }
    artifacts[Path("contracts/manifest-v1.json")] = _json(
        {
            "contractVersion": CONTRACT_VERSION,
            "artifacts": checksums,
        }
    )
    return artifacts


def export(root: Path, *, check: bool) -> int:
    mismatches: list[str] = []
    for relative, content in build_artifacts().items():
        target = root / relative
        if check:
            if not target.exists() or target.read_text() != content:
                mismatches.append(str(relative))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)

    if mismatches:
        raise SystemExit(
            "Contract artifacts are stale or missing: " + ", ".join(mismatches)
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    return export(args.root.resolve(), check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
