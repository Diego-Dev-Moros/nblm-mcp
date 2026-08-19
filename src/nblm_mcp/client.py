"""Lifecycle for the shared NotebookLMClient.

The upstream client is async re-entrant but bound to the event loop it was
opened on, and it is not thread-safe. FastMCP serves every tool call on one
loop, so a single long-lived client is both correct and much cheaper than
re-reading the cookie store per call — but we still verify loop identity and
rebuild if a host ever runs us on a fresh loop.
"""

from __future__ import annotations

import asyncio
from typing import Any

from nblm_mcp.config import Config, load_config

_lock = asyncio.Lock()
_client: Any = None
_context: Any = None
_loop: asyncio.AbstractEventLoop | None = None
_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = load_config()
    return _config


async def get_client() -> Any:
    """Return the shared client, opening it on first use."""
    global _client, _context, _loop

    loop = asyncio.get_running_loop()
    async with _lock:
        if _client is not None and _loop is loop:
            return _client
        if _client is not None:
            await _close_locked()

        from notebooklm import NotebookLMClient

        cfg = get_config()
        context = NotebookLMClient.from_storage(cfg.storage_path, profile=cfg.profile)
        _client = await context.__aenter__()
        _context = context
        _loop = loop
        return _client


async def _close_locked() -> None:
    global _client, _context, _loop
    context, _context = _context, None
    _client = None
    _loop = None
    if context is not None:
        try:
            await context.__aexit__(None, None, None)
        except Exception:  # noqa: BLE001 - closing must never mask the real error
            pass


async def reset() -> None:
    """Drop the cached client so the next call re-reads the cookie store."""
    global _config
    async with _lock:
        await _close_locked()
    _config = None
