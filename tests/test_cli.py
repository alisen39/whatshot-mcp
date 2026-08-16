from __future__ import annotations

from typing import Any

from whatshot_mcp import __version__, cli
from whatshot_mcp.config import Settings
from whatshot_mcp.contracts.v1 import BackendCapabilities
from whatshot_mcp.errors import BackendBoardKeyVersionError, BackendTransportError


def test_version_command(capsys: Any) -> None:
    assert cli.main(["version"]) == cli.EXIT_OK
    assert capsys.readouterr().out.strip() == f"whatshot-mcp {__version__}"


def test_serve_subcommand_applies_http_overrides(monkeypatch: Any) -> None:
    calls: list[tuple[str, int]] = []

    def fake_run(settings: Settings) -> None:
        calls.append((settings.server.bind, settings.server.port))

    monkeypatch.setattr(cli, "run", fake_run)
    assert cli.main(["serve", "--host", "127.0.0.1", "--port", "7001"]) == 0
    assert calls == [("127.0.0.1", 7001)]


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
