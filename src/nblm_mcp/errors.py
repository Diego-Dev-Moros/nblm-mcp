"""Translate notebooklm-py exceptions into agent-readable tool errors."""

from __future__ import annotations

from fastmcp.exceptions import ToolError

LOGIN_HINT = (
    "Run `nblm-mcp-login` in a terminal (it opens a browser window), then retry. "
    "The MCP server never logs in on its own."
)


def _is_missing_session(exc: Exception) -> bool:
    """True when a FileNotFoundError is about the cookie store, not user data."""
    message = str(exc).lower()
    return "storage" in message or "login" in message


def to_tool_error(exc: Exception) -> ToolError:
    """Map a library exception to a ToolError carrying an actionable message.

    Unknown exception types are passed through with their own message rather
    than swallowed — the caller is expected to re-raise the result.
    """
    from notebooklm import exceptions as nblm

    if isinstance(exc, FileNotFoundError) and _is_missing_session(exc):
        # The library raises a bare FileNotFoundError when no cookie store
        # exists yet, and points at its own CLI. Answer in our own terms.
        return ToolError(f"No NotebookLM session stored yet. {LOGIN_HINT}")
    if isinstance(exc, (nblm.AuthError, nblm.AuthExtractionError)):
        return ToolError(f"NotebookLM session is missing or expired. {LOGIN_HINT}")
    if isinstance(exc, nblm.NotFoundError):
        return ToolError(
            f"{exc} — the id may be wrong, or the item belongs to another Google account. "
            "Call list_notebooks to see what this session can reach."
        )
    if isinstance(exc, nblm.RateLimitError):
        return ToolError(
            f"Google rate-limited this account: {exc}. Wait a few minutes before retrying; "
            "NotebookLM enforces daily quotas on chat and Studio generation."
        )
    if isinstance(exc, nblm.NotebookLimitError):
        return ToolError(f"Account limit reached: {exc}")
    if isinstance(exc, nblm.WaitTimeoutError):
        return ToolError(
            f"Timed out waiting for NotebookLM: {exc}. The work usually keeps running "
            "server-side — poll with list_artifacts or list_sources instead of retrying."
        )
    if isinstance(exc, nblm.MissingDependencyError):
        return ToolError(f"Optional dependency missing: {exc}")
    if isinstance(exc, nblm.NetworkError):
        return ToolError(f"Network error talking to NotebookLM: {exc}")
    if isinstance(exc, (nblm.ValidationError, nblm.ConfigurationError)):
        return ToolError(str(exc))
    if isinstance(exc, nblm.NotebookLMError):
        return ToolError(
            f"NotebookLM call failed: {exc}. This server drives Google's undocumented "
            "internal API, which can change without notice."
        )
    return ToolError(str(exc) or exc.__class__.__name__)
