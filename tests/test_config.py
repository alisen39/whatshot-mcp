from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from whatshot_mcp.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def test_example_config_loads_without_optional_dependencies() -> None:
    settings = Settings.load(ROOT / "config.example.toml", environ={})
    assert settings.backend.url == "http://127.0.0.1:6690/api/v1"
    assert settings.backend.api_key is None
    assert settings.server.path == "/mcp"


def test_environment_overrides_toml_and_secret_is_not_represented(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        """
[server]
bind = "127.0.0.1"
port = 6691
path = "/mcp"

[backend]
url = "http://127.0.0.1:6690/api/v1"
api_key_env = "CUSTOM_BACKEND_KEY"
api_key = "config-secret"
timeout_seconds = 15
capabilities_ttl_seconds = 60
""".strip(),
        encoding="utf-8",
    )
    settings = Settings.load(
        config,
        environ={
            "WHATSHOT_MCP_SERVER_PORT": "7777",
            "WHATSHOT_MCP_BACKEND_URL": "https://api.whatshot.top/api/v1",
            "CUSTOM_BACKEND_KEY": "super-secret",
        },
    )
    assert settings.server.port == 7777
    assert settings.backend.url == "https://api.whatshot.top/api/v1"
    assert settings.backend.api_key is not None
    assert settings.backend.api_key.get_secret_value() == "super-secret"
    assert "super-secret" not in repr(settings)
    assert "config-secret" not in repr(settings)


@pytest.mark.parametrize(
    "url",
    [
        "http://api.whatshot.top/api/v1",
        "https://user:secret@api.whatshot.top/api/v1",
        "https://api.whatshot.top/backend/v1",
        "https://api.whatshot.top/api/v1?token=secret",
    ],
)
def test_backend_url_fails_closed(url: str) -> None:
    with pytest.raises(ValidationError):
        Settings.load(environ={"WHATSHOT_MCP_BACKEND_URL": url})


def test_streamable_http_cannot_bind_publicly_without_inbound_auth() -> None:
    settings = Settings.load(environ={"WHATSHOT_MCP_SERVER_BIND": "0.0.0.0"})
    with pytest.raises(ValueError, match="non-loopback"):
        settings.assert_streamable_http_safe()


def test_bearer_passthrough_allows_non_loopback_without_shared_secrets() -> None:
    settings = Settings.load(
        environ={
            "WHATSHOT_MCP_SERVER_BIND": "0.0.0.0",
            "WHATSHOT_MCP_SERVER_AUTH_MODE": "bearer_passthrough",
        }
    )
    settings.server.allowed_hosts = ["mcp.whatshot.top"]
    settings.assert_streamable_http_safe()
    assert settings.server.auth.mode == "bearer_passthrough"


def test_non_loopback_bearer_passthrough_requires_allowed_hosts() -> None:
    settings = Settings.load(
        environ={
            "WHATSHOT_MCP_SERVER_BIND": "0.0.0.0",
            "WHATSHOT_MCP_SERVER_AUTH_MODE": "bearer_passthrough",
        }
    )
    with pytest.raises(ValueError, match="requires server.allowed_hosts"):
        settings.assert_streamable_http_safe()


def test_bearer_passthrough_forbids_shared_backend_key() -> None:
    settings = Settings.load(
        environ={
            "WHATSHOT_MCP_SERVER_AUTH_MODE": "bearer_passthrough",
            "WHATSHOT_MCP_BACKEND_API_KEY": "shared-backend-key",
        }
    )
    with pytest.raises(ValueError, match="forbids a static Backend key"):
        settings.assert_streamable_http_safe()


def test_removed_static_token_mode_and_oauth_fail_closed() -> None:
    with pytest.raises(ValidationError):
        Settings.load(environ={"WHATSHOT_MCP_SERVER_AUTH_MODE": "static_token"})
    oauth = Settings.load(environ={"WHATSHOT_MCP_SERVER_AUTH_MODE": "oauth"})
    with pytest.raises(ValueError, match="not implemented"):
        oauth.assert_streamable_http_safe()
