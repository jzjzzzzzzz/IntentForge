import stat

from intentforge.config import (
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_OPENAI_MODEL,
    load_llm_config,
    load_user_config,
    mask_secret,
    save_llm_config,
)
from intentforge.llm.provider import OpenAICompatibleProvider, load_provider_from_env


def test_save_llm_config_persists_owner_only_file(tmp_path) -> None:
    config_path = tmp_path / "config.json"

    saved_path = save_llm_config(
        provider="openai-compatible",
        base_url=DEFAULT_OPENAI_BASE_URL,
        model=DEFAULT_OPENAI_MODEL,
        api_key="sk-test123456789",
        path=config_path,
    )

    assert saved_path == config_path
    assert load_user_config(config_path)["llm"]["model"] == DEFAULT_OPENAI_MODEL
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600


def test_load_llm_config_accepts_standard_openai_api_key(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("INTENTFORGE_CONFIG_PATH", str(tmp_path / "missing.json"))
    monkeypatch.delenv("INTENTFORGE_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("INTENTFORGE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("INTENTFORGE_LLM_MODEL", raising=False)
    monkeypatch.delenv("INTENTFORGE_LLM_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai123456789")

    config = load_llm_config()

    assert config["provider"] == "openai-compatible"
    assert config["api_key"] == "sk-openai123456789"
    assert config["base_url"] == DEFAULT_OPENAI_BASE_URL
    assert config["model"] == DEFAULT_OPENAI_MODEL


def test_empty_user_config_is_treated_as_unconfigured(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("", encoding="utf-8")

    assert load_user_config(config_path) == {}


def test_load_provider_from_saved_config(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.json"
    save_llm_config(
        provider="openai-compatible",
        base_url="https://api.openai.com/v1",
        model="gpt-test",
        api_key="sk-config123456789",
        path=config_path,
    )
    monkeypatch.setenv("INTENTFORGE_CONFIG_PATH", str(config_path))
    monkeypatch.delenv("INTENTFORGE_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("INTENTFORGE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("INTENTFORGE_LLM_MODEL", raising=False)
    monkeypatch.delenv("INTENTFORGE_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    provider = load_provider_from_env()

    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.model == "gpt-test"
    assert provider.api_key == "sk-config123456789"


def test_mask_secret() -> None:
    assert mask_secret("") == ""
    assert mask_secret("short") == "***"
    assert mask_secret("sk-1234567890abcdef") == "sk-123...cdef"
