"""TOML configuration with explicit environment overrides."""

from __future__ import annotations

import ipaddress
import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ServerAuthSettings(ConfigModel):
    mode: Literal["none", "bearer_passthrough", "oauth"] = "none"


class ServerSettings(ConfigModel):
    bind: str = "127.0.0.1"
    port: int = Field(default=6691, ge=1, le=65535)
    path: str = "/mcp"
    allowed_hosts: list[str] = Field(default_factory=list)
    allowed_origins: list[str] = Field(default_factory=list)
    auth: ServerAuthSettings = Field(default_factory=ServerAuthSettings)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not value.startswith("/") or "?" in value or "#" in value:
            raise ValueError("server.path must be an absolute URL path")
        return value

    @field_validator("allowed_hosts", "allowed_origins")
    @classmethod
    def validate_security_values(cls, values: list[str]) -> list[str]:
        if any(not value or value != value.strip() for value in values):
            raise ValueError("transport security values must be non-empty and trimmed")
        return values


class BackendSettings(ConfigModel):
    url: str = "http://127.0.0.1:6690/api/v1"
    api_key_env: str = "WHATSHOT_MCP_BACKEND_API_KEY"
    api_key: SecretStr | None = Field(default=None, exclude=True, repr=False)
    timeout_seconds: float = Field(default=15.0, gt=0, le=300)
    capabilities_ttl_seconds: float = Field(default=60.0, ge=0, le=3600)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("backend.url must be an HTTP(S) URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError(
                "backend.url must not contain credentials, query, or fragment"
            )
        if parsed.scheme == "http" and not _is_loopback(parsed.hostname):
            raise ValueError("non-loopback backend.url must use HTTPS")
        path = parsed.path.rstrip("/")
        if not path.endswith("/api/v1"):
            raise ValueError("backend.url must end with /api/v1")
        return value.rstrip("/")


class ToolSettings(ConfigModel):
    max_result_items: int = Field(default=200, ge=1, le=200)
    default_history_days: int = Field(default=7, ge=1, le=3650)
    max_analysis_scan_items: int = Field(default=2000, ge=1)


class Settings(BaseSettings):
    """Fully resolved process settings.

    Environment overrides are applied explicitly so nested settings remain
    predictable and testable. Unknown TOML keys fail closed.
    """

    model_config = SettingsConfigDict(extra="forbid")

    server: ServerSettings = Field(default_factory=ServerSettings)
    backend: BackendSettings = Field(default_factory=BackendSettings)
    tools: ToolSettings = Field(default_factory=ToolSettings)

    @classmethod
    def load(
        cls,
        path: str | Path | None = None,
        *,
        environ: Mapping[str, str] | None = None,
    ) -> Settings:
        env = os.environ if environ is None else environ
        raw: dict[str, Any] = {}
        if path is not None:
            config_path = Path(path).expanduser()
            with config_path.open("rb") as handle:
                parsed = tomllib.load(handle)
            if not isinstance(parsed, dict):
                raise ValueError("configuration root must be a TOML table")
            raw = parsed

        _apply_env_overrides(raw, env)
        settings = cls.model_validate(raw)
        api_key = env.get("WHATSHOT_MCP_BACKEND_API_KEY")
        if api_key is None and settings.backend.api_key_env:
            api_key = env.get(settings.backend.api_key_env)
        if api_key:
            settings.backend.api_key = SecretStr(api_key)
        return settings

    def assert_streamable_http_safe(self) -> None:
        auth = self.server.auth
        if auth.mode == "oauth":
            raise ValueError("server.auth.mode=oauth is not implemented")
        if auth.mode == "bearer_passthrough":
            if self.backend.api_key is not None:
                raise ValueError(
                    "server.auth.mode=bearer_passthrough forbids a static Backend key"
                )
            if not _is_loopback(self.server.bind) and not self.server.allowed_hosts:
                raise ValueError(
                    "non-loopback bearer_passthrough requires server.allowed_hosts"
                )
            return
        if not _is_loopback(self.server.bind):
            raise ValueError(
                "non-loopback Streamable HTTP requires "
                "server.auth.mode=bearer_passthrough"
            )


_ENV_PATHS: dict[str, tuple[str, str, Any]] = {
    "WHATSHOT_MCP_SERVER_BIND": ("server", "bind", str),
    "WHATSHOT_MCP_SERVER_PORT": ("server", "port", int),
    "WHATSHOT_MCP_SERVER_PATH": ("server", "path", str),
    "WHATSHOT_MCP_SERVER_AUTH_MODE": ("server.auth", "mode", str),
    "WHATSHOT_MCP_BACKEND_URL": ("backend", "url", str),
    "WHATSHOT_MCP_BACKEND_API_KEY_ENV": ("backend", "api_key_env", str),
    "WHATSHOT_MCP_BACKEND_TIMEOUT_SECONDS": (
        "backend",
        "timeout_seconds",
        float,
    ),
    "WHATSHOT_MCP_BACKEND_CAPABILITIES_TTL_SECONDS": (
        "backend",
        "capabilities_ttl_seconds",
        float,
    ),
}


def _apply_env_overrides(raw: dict[str, Any], env: Mapping[str, str]) -> None:
    for variable, (section, key, converter) in _ENV_PATHS.items():
        if variable not in env:
            continue
        if "." in section:
            parent, child = section.split(".", 1)
            parent_value = raw.setdefault(parent, {})
            if not isinstance(parent_value, dict):
                raise ValueError(f"configuration section {parent!r} must be a table")
            section_value = parent_value.setdefault(child, {})
        else:
            section_value = raw.setdefault(section, {})
        if not isinstance(section_value, dict):
            raise ValueError(f"configuration section {section!r} must be a table")
        section_value[key] = converter(env[variable])


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
