"""User configuration helpers for IntentForge.

The deterministic CAD core does not require user configuration.  This module
only stores optional client/runtime preferences such as LLM provider settings.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


CONFIG_PATH_ENV = "INTENTFORGE_CONFIG_PATH"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-5.5"


def default_config_path() -> Path:
    """Return the default per-user IntentForge config path."""

    override = os.environ.get(CONFIG_PATH_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".intentforge" / "config.json"


def load_user_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load user config JSON, returning an empty config when absent."""

    config_path = Path(path).expanduser() if path is not None else default_config_path()
    if not config_path.exists():
        return {}
    raw_config = config_path.read_text(encoding="utf-8").strip()
    if not raw_config:
        return {}
    data = json.loads(raw_config)
    if not isinstance(data, dict):
        raise ValueError(f"IntentForge config must be a JSON object: {config_path}")
    return data


def save_user_config(config: dict[str, Any], path: str | Path | None = None) -> Path:
    """Persist user config with owner-only file permissions where supported."""

    config_path = Path(path).expanduser() if path is not None else default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        config_path.chmod(0o600)
    except OSError:
        # Permission changes are best-effort on non-POSIX filesystems.
        pass
    return config_path


def mask_secret(value: str) -> str:
    """Mask a secret for terminal display."""

    if not value:
        return ""
    if len(value) <= 10:
        return "***"
    return f"{value[:6]}...{value[-4:]}"


def load_llm_config(path: str | Path | None = None) -> dict[str, str]:
    """Resolve optional LLM config from env vars, OpenAI env, then user config.

    IntentForge-specific environment variables take precedence.  The standard
    OPENAI_API_KEY variable is accepted as a convenience for OpenAI users.
    """

    user_config = load_user_config(path)
    llm_config = user_config.get("llm", {})
    if not isinstance(llm_config, dict):
        llm_config = {}

    provider = (
        os.environ.get("INTENTFORGE_LLM_PROVIDER", "").strip()
        or str(llm_config.get("provider", "")).strip()
    )
    api_key = (
        os.environ.get("INTENTFORGE_LLM_API_KEY", "").strip()
        or os.environ.get("OPENAI_API_KEY", "").strip()
        or str(llm_config.get("api_key", "")).strip()
    )

    if not provider and api_key:
        provider = "openai-compatible"

    base_url = (
        os.environ.get("INTENTFORGE_LLM_BASE_URL", "").strip()
        or str(llm_config.get("base_url", "")).strip()
    )
    model = (
        os.environ.get("INTENTFORGE_LLM_MODEL", "").strip()
        or str(llm_config.get("model", "")).strip()
    )

    if provider.lower() in {"openai", "openai-compatible", "compatible"}:
        base_url = base_url or DEFAULT_OPENAI_BASE_URL
        model = model or DEFAULT_OPENAI_MODEL

    return {
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "api_key": api_key,
    }


def save_llm_config(
    *,
    provider: str,
    base_url: str = "",
    model: str = "",
    api_key: str = "",
    path: str | Path | None = None,
) -> Path:
    """Merge and save LLM settings into the user config."""

    config = load_user_config(path)
    config["llm"] = {
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "api_key": api_key,
    }
    return save_user_config(config, path)


def llm_configured(path: str | Path | None = None) -> bool:
    """Return True when a usable optional LLM provider is configured."""

    config = load_llm_config(path)
    provider = config["provider"].lower()
    if provider == "mock":
        return True
    if provider in {"openai", "openai-compatible", "compatible"}:
        return bool(config["api_key"] and config["model"])
    return False
