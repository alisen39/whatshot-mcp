"""Sanitized public errors for Backend and MCP boundaries."""

from __future__ import annotations

from typing import Any

from whats_hot_mcp.contracts.v1 import BackendErrorCode


class BackendClientError(RuntimeError):
    """Base error safe to expose through an MCP tool error boundary."""

    def __init__(
        self,
        code: BackendErrorCode,
        message: str,
        *,
        retryable: bool = False,
        status_code: int | None = None,
        request_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.status_code = status_code
        self.request_id = request_id
        self.details = details

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"


class BackendAPIError(BackendClientError):
    """A valid stable error envelope returned by the Backend."""


class BackendProtocolError(BackendClientError):
    """The Backend response did not conform to Contract v1."""

    def __init__(
        self, message: str = "Backend returned an invalid Contract v1 response."
    ) -> None:
        super().__init__(BackendErrorCode.UPSTREAM_UNAVAILABLE, message, retryable=True)


class BackendBoardKeyVersionError(BackendProtocolError):
    """The Backend speaks Contract v1 but uses another board-key identity."""

    def __init__(self) -> None:
        super().__init__("Backend boardKeyVersion is incompatible with this MCP.")


class BackendTransportError(BackendClientError):
    """The Backend could not be reached without exposing transport internals."""

    def __init__(self, message: str = "WhatsHot Backend is unavailable.") -> None:
        super().__init__(BackendErrorCode.UPSTREAM_UNAVAILABLE, message, retryable=True)


class UnsupportedCapability(BackendClientError):
    """A fixed tool is unavailable on the configured Backend deployment."""

    def __init__(self, capability: str) -> None:
        super().__init__(
            BackendErrorCode.CAPABILITY_UNAVAILABLE,
            f"Backend does not support capability '{capability}'.",
            retryable=False,
            details={"capability": capability},
        )
        self.capability = capability
