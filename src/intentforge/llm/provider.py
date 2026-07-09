"""LLM provider interface and optional provider loading."""

from __future__ import annotations

from abc import ABC, abstractmethod
import json
from typing import Any
from urllib import request as urllib_request

from intentforge.config import load_llm_config


class LLMProviderUnavailableError(RuntimeError):
    """Raised when an LLM workflow is requested without a configured provider."""


class LLMProvider(ABC):
    """Abstract JSON-completion provider used by the optional LLM translator."""

    @abstractmethod
    def complete_json(self, messages: list[dict[str, str]], schema_name: str) -> dict[str, Any]:
        """Return a JSON object for a named translation schema."""


class OpenAICompatibleProvider(LLMProvider):
    """Minimal OpenAI-compatible chat completions provider.

    This provider is optional and is never used in tests unless explicitly
    configured by environment variables.

    Compatible with OpenAI, DeepSeek, Moonshot, Qwen, and any service
    that follows the OpenAI Chat Completions API format.  The ``developer``
    role (OpenAI-specific) is mapped to ``system`` for providers that
    do not support it.
    """

    # Roles that are OpenAI-specific and must be mapped to supported
    # equivalents for broader provider compatibility.
    _ROLE_MAP = {
        "developer": "system",
    }

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _normalize_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
        """Map unsupported roles to their nearest compatible equivalent."""
        normalized: list[dict[str, str]] = []
        for msg in messages:
            role = msg.get("role", "user")
            mapped_role = OpenAICompatibleProvider._ROLE_MAP.get(role, role)
            normalized.append({"role": mapped_role, "content": msg.get("content", "")})
        return normalized

    def complete_json(self, messages: list[dict[str, str]], schema_name: str) -> dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        normalized = self._normalize_messages(messages)
        payload = {
            "model": self.model,
            "messages": normalized,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib_request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib_request.urlopen(req, timeout=self.timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("LLM response JSON must be an object.")
        return parsed


def load_provider_from_env() -> LLMProvider | None:
    """Load an optional LLM provider from env vars or user config."""

    config = load_llm_config()
    provider_name = config["provider"].strip().lower()
    if not provider_name:
        return None
    if provider_name == "mock":
        from intentforge.llm.mock_provider import MockLLMProvider

        return MockLLMProvider()
    if provider_name in {"openai", "openai-compatible", "compatible"}:
        api_key = config["api_key"]
        base_url = config["base_url"]
        model = config["model"]
        if not api_key or not model:
            raise LLMProviderUnavailableError(
                "INTENTFORGE_LLM_API_KEY and INTENTFORGE_LLM_MODEL are required for the OpenAI-compatible provider."
            )
        return OpenAICompatibleProvider(base_url=base_url, api_key=api_key, model=model)
    raise LLMProviderUnavailableError(f"Unsupported LLM provider: {provider_name}")
