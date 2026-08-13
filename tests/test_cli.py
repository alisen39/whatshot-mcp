from __future__ import annotations

from typing import Any

from whats_hot_mcp import __version__, cli
from whats_hot_mcp.config import Settings
from whats_hot_mcp.contracts.v1 import BackendCapabilities
from whats_hot_mcp.errors import BackendBoardKeyVersionError, BackendTransportError


def test_version_command(capsys: Any) -> None:
    assert cli.main(["version"]) == cli.EXIT_OK
    assert capsys.readouterr().out.strip() == f"whats-hot-mcp {__version__}"


def test_serve_subcommand_and_legacy_form_are_compatible(
    monkeypatch: Any,
) -> None:
    calls: list[tuple[str, int, str]] = []

    def fake_run(settings: Settings, transport: str) -> None:
        calls.append((settings.server.bind, settings.server.port, transport))

    monkeypatch.setattr(cli, "run", fake_run)
    assert cli.main(["serve", "--host", "127.0.0.1", "--port", "7001"]) == 0
    assert cli.main(["--host", "127.0.0.1", "--port", "7002"]) == 0
    assert cli.main(["serve", "--transport", "stdio"]) == 0
    assert calls == [
        ("127.0.0.1", 7001, "streamable-http"),
        ("127.0.0.1", 7002, "streamable-http"),
        ("127.0.0.1", 6691, "stdio"),
    ]


def test_config_validate_and_secret_safe_error(monkeypatch: Any, capsys: Any) -> None:
    assert cli.main(["config", "validate"]) == cli.EXIT_OK
    assert "configuration valid" in capsys.readouterr().out

    def bad_settings(_path: object) -> Settings:
        raise ValueError("leaked-super-secret")

    monkeypatch.setattr(cli, "_load_settings", bad_settings)
    assert cli.main(["config", "validate"]) == cli.EXIT_CONFIG_ERROR
    captured = capsys.readouterr()
    assert "leaked-super-secret" not in captured.err


class FakeBackend:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    async def __aenter__(self) -> FakeBackend:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def get_capabilities(
        self, *, force_refresh: bool = False
    ) -> BackendCapabilities:
        assert force_refresh is True
        return BackendCapabilities.model_validate(
            {
                "backend": {"name": "checked", "version": "1.2.3"},
                "boardKeyVersion": 1,
                "profiles": ["core-read"],
                "features": {
                    "sources": True,
                    "sourceSchema": True,
                    "current": True,
                    "kinds": ["hotlist"],
                },
            }
        )


def test_backend_check_success_and_explicit_unavailable_exit(
    monkeypatch: Any, capsys: Any
) -> None:
    monkeypatch.setattr(cli, "BackendClient", FakeBackend)
    assert cli.main(["backend", "check"]) == cli.EXIT_OK
    assert "boardKeyVersion=1" in capsys.readouterr().out

    class UnavailableBackend(FakeBackend):
        async def get_capabilities(
            self, *, force_refresh: bool = False
        ) -> BackendCapabilities:
            raise BackendTransportError("safe unavailable")

    monkeypatch.setattr(cli, "BackendClient", UnavailableBackend)
    assert cli.main(["backend", "check"]) == cli.EXIT_BACKEND_UNAVAILABLE
    assert "safe unavailable" in capsys.readouterr().err

    class IncompatibleBackend(FakeBackend):
        async def get_capabilities(
            self, *, force_refresh: bool = False
        ) -> BackendCapabilities:
            raise BackendBoardKeyVersionError()

    monkeypatch.setattr(cli, "BackendClient", IncompatibleBackend)
    assert cli.main(["backend", "check"]) == cli.EXIT_BOARD_KEY_INCOMPATIBLE
    assert "boardKeyVersion" in capsys.readouterr().err
