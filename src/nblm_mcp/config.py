from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_DOWNLOAD_DIR = Path.home() / ".nblm-mcp" / "downloads"


@dataclass(frozen=True)
class Config:
    profile: str | None = None
    storage_path: str | None = None
    download_dir: Path = DEFAULT_DOWNLOAD_DIR
    generation_timeout: float = 600.0
    source_timeout: float = 180.0


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def load_config() -> Config:
    """Load configuration from environment variables (.env in cwd is honored)."""
    env_path = Path.cwd() / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    download_dir = os.getenv("NBLM_DOWNLOAD_DIR")
    return Config(
        profile=os.getenv("NOTEBOOKLM_PROFILE") or None,
        storage_path=os.getenv("NOTEBOOKLM_STORAGE_PATH") or None,
        download_dir=Path(download_dir).expanduser() if download_dir else DEFAULT_DOWNLOAD_DIR,
        generation_timeout=_float_env("NBLM_GENERATION_TIMEOUT", 600.0),
        source_timeout=_float_env("NBLM_SOURCE_TIMEOUT", 180.0),
    )
