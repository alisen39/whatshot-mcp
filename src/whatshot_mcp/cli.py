"""Command-line entry point for local and hosted deployments."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

import uvicorn

from whatshot_mcp import __version__
from whatshot_mcp.backend import BackendClient
from whatshot_mcp.config import Settings
from whatshot_mcp.contracts.v1 import BOARD_KEY_VERSION, BackendCapabilities
from whatshot_mcp.errors import (
    BackendBoardKeyVersionError,
    BackendClientError,
    BackendTransportError,
)
from whatshot_mcp.server import build_mcp_server, build_streamable_http_app

EXIT_OK = 0
EXIT_CONFIG_ERROR = 2
EXIT_BACKEND_UNAVAILABLE = 3
EXIT_BACKEND_CONTRACT_ERROR = 4
EXIT_BOARD_KEY_INCOMPATIBLE = 5


def _add_config(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path)


def _add_serve_options(parser: argparse.ArgumentParser) -> None:
    _add_config(parser)
    parser.add_argument("--host", help="override server.bind")
    parser.add_argument("--port", type=int, help="override server.port")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="whatshot-mcp")
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser("serve", help="start the MCP server")
    _add_serve_options(serve)

    config = commands.add_parser("config", help="configuration operations")
    config_commands = config.add_subparsers(dest="config_command", required=True)
    config_validate = config_commands.add_parser("validate", help="validate config")
    _add_config(config_validate)

    backend = commands.add_parser("backend", help="Backend operations")
    backend_commands = backend.add_subparsers(dest="backend_command", required=True)
    backend_check = backend_commands.add_parser("check", help="check Backend Contract")
    _add_config(backend_check)

    commands.add_parser("version", help="print package version")
    return parser


def _load_settings(path: Path | None) -> Settings:
    return Settings.load(path)


def _apply_serve_overrides(settings: Settings, args: argparse.Namespace) -> None:
    if args.host is not None:
        settings.server.bind = args.host
    if args.port is not None:
        settings.server.port = args.port


def run(settings: Settings) -> None:
    settings.assert_streamable_http_safe()
    capabilities = asyncio.run(_load_startup_capabilities(settings))
    backend = BackendClient(
        settings.backend.url,
        api_key=settings.backend.api_key,
        timeout_seconds=settings.backend.timeout_seconds,
        capabilities_ttl_seconds=settings.backend.capabilities_ttl_seconds,
    )
    inbound_token = (
        settings.server.auth.token
        if settings.server.auth.mode == "static_token"
        else None
    )
    server = build_mcp_server(
        backend,
        capabilities,
        close_backend_on_shutdown=True,
    )
    app = build_streamable_http_app(
        server,
        path=settings.server.path,
        host=settings.server.bind,
        inbound_token=inbound_token,
    )
    uvicorn.run(
        app,
        host=settings.server.bind,
        port=settings.server.port,
    )


async def _load_startup_capabilities(settings: Settings) -> BackendCapabilities:
    """Use a short-lived client so the runtime client belongs to its serve loop."""

    async with BackendClient(
        settings.backend.url,
        api_key=settings.backend.api_key,
        timeout_seconds=settings.backend.timeout_seconds,
        capabilities_ttl_seconds=0,
    ) as backend:
        return await backend.get_capabilities(force_refresh=True)


async def _check_backend(settings: Settings) -> int:
    try:
        async with BackendClient(
            settings.backend.url,
            api_key=settings.backend.api_key,
            timeout_seconds=settings.backend.timeout_seconds,
            capabilities_ttl_seconds=0,
        ) as backend:
            capabilities = await backend.get_capabilities(force_refresh=True)
    except BackendTransportError as exc:
        print(f"backend unavailable: {exc}", file=sys.stderr)
        return EXIT_BACKEND_UNAVAILABLE
    except BackendBoardKeyVersionError as exc:
        print(f"backend compatibility check failed: {exc}", file=sys.stderr)
        return EXIT_BOARD_KEY_INCOMPATIBLE
    except BackendClientError as exc:
        print(f"backend contract check failed: {exc}", file=sys.stderr)
        return EXIT_BACKEND_CONTRACT_ERROR

    if capabilities.board_key_version != BOARD_KEY_VERSION:
        print(
            "backend boardKeyVersion is incompatible with this MCP",
            file=sys.stderr,
        )
        return EXIT_BOARD_KEY_INCOMPATIBLE
    profiles = ",".join(sorted(profile.value for profile in capabilities.profiles))
    print(
        f"backend ok: {capabilities.backend.name} {capabilities.backend.version}; "
        f"contract=1; boardKeyVersion={capabilities.board_key_version}; "
        f"profiles={profiles}"
    )
    return EXIT_OK


def _configuration_error() -> int:
    # Configuration exceptions may echo invalid input. Keep this boundary
    # deliberately generic so API keys and static tokens never reach stderr.
    print("configuration invalid", file=sys.stderr)
    return EXIT_CONFIG_ERROR


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "version":
        print(f"whatshot-mcp {__version__}")
        return EXIT_OK

    try:
        settings = _load_settings(args.config)
    except Exception:
        return _configuration_error()

    if args.command == "config":
        try:
            settings.assert_streamable_http_safe()
        except ValueError:
            return _configuration_error()
        print("configuration valid")
        return EXIT_OK

    if args.command == "backend":
        return asyncio.run(_check_backend(settings))

    _apply_serve_overrides(settings, args)
    try:
        run(settings)
    except ValueError:
        return _configuration_error()
    except BackendTransportError as exc:
        print(f"backend unavailable: {exc}", file=sys.stderr)
        return EXIT_BACKEND_UNAVAILABLE
    except BackendBoardKeyVersionError as exc:
        print(f"backend compatibility check failed: {exc}", file=sys.stderr)
        return EXIT_BOARD_KEY_INCOMPATIBLE
    except BackendClientError as exc:
        print(f"backend contract check failed: {exc}", file=sys.stderr)
        return EXIT_BACKEND_CONTRACT_ERROR
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
