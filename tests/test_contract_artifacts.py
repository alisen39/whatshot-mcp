from __future__ import annotations

from pathlib import Path

from whatshot_mcp.contracts.export import build_artifacts, build_openapi


def test_committed_contract_artifacts_are_current() -> None:
    root = Path(__file__).parents[1]
    expected = build_artifacts()

    assert expected
    for relative, content in expected.items():
        assert (root / relative).read_text() == content, relative


def test_openapi_contains_cloud_navigation_contract() -> None:
    openapi = build_openapi()

    navigation = openapi["paths"]["/navigation"]["get"]
    category = openapi["paths"]["/category/current"]["post"]
    assert navigation["operationId"] == "listNavigation"
    assert navigation["x-whatshot-required-scopes"] == ["data:read"]
    assert category["operationId"] == "fetchCategoryCurrent"
    assert category["x-whatshot-required-scopes"] == ["data:read"]


def test_openapi_models_backend_auth_as_a_deployment_policy() -> None:
    openapi = build_openapi()

    assert openapi["security"] == [{}, {"bearerAuth": []}]
    policy = openapi["x-whatshot-deployment-auth"]
    assert policy["selection"] == "deployment"
    assert policy["capabilitiesPublic"] is True
    assert policy["policies"]["core"]["bearerRequired"] is False
    assert policy["policies"]["cloud"]["bearerRequired"] is True
    assert openapi["paths"]["/capabilities"]["get"]["security"] == []

    data_operations = {
        ("/sources", "get"),
        ("/sources/{site}", "get"),
        ("/current", "post"),
        ("/current/batch", "post"),
        ("/navigation", "get"),
        ("/category/current", "post"),
        ("/history", "get"),
        ("/history/search", "get"),
        ("/history/trends", "get"),
        ("/coverage", "get"),
    }
    for path, method in data_operations:
        operation = openapi["paths"][path][method]
        assert operation["x-whatshot-required-scopes"] == ["data:read"]
        assert "security" not in operation
