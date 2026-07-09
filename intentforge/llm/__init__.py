"""Optional LLM intent translation layer for IntentForge."""

from intentforge.llm.mock_provider import MockLLMProvider
from intentforge.llm.provider import (
    LLMProvider,
    LLMProviderUnavailableError,
    OpenAICompatibleProvider,
    load_provider_from_env,
)
from intentforge.llm.translator import (
    translate_edit_apply,
    translate_edit_to_request,
    translate_prompt_to_build,
    translate_prompt_to_intent,
)

__all__ = [
    "LLMProvider",
    "LLMProviderUnavailableError",
    "MockLLMProvider",
    "OpenAICompatibleProvider",
    "load_provider_from_env",
    "translate_edit_apply",
    "translate_edit_to_request",
    "translate_prompt_to_build",
    "translate_prompt_to_intent",
]
