"""WhatsHot MCP public package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("whats-hot-mcp")
except PackageNotFoundError:  # pragma: no cover - source tree without install
    __version__ = "0.2.0"

__all__ = ["__version__"]
