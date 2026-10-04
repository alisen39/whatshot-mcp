"""WhatsHot MCP public package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("whatshot-mcp")
except PackageNotFoundError:  # pragma: no cover - source tree without install
    __version__ = "0.4.0"

__all__ = ["__version__"]
