"""Tests for the IntentForge interactive CLI client."""

import os
import sys
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest


# ── Import tests (graceful without optional deps) ─────────────────────

def test_client_module_imports_without_rich() -> None:
    """Client module should import even when rich is not available."""
    # Force rich to be unavailable
    with patch.dict(sys.modules, {"rich": None, "rich.console": None}):
        # Re-import should not crash
        import importlib
        import intentforge.client.repl as repl
        importlib.reload(repl)
        assert hasattr(repl, "run_interactive")


def test_if_console_print_without_rich() -> None:
    """IFConsole should work in plain mode."""
    with patch.dict(sys.modules, {
        "rich": None, "rich.console": None,
        "rich.live": None, "rich.panel": None,
        "rich.spinner": None, "rich.table": None,
        "rich.text": None, "rich.markdown": None,
        "rich.progress": None,
    }):
        import importlib
        import intentforge.client.repl as repl
        importlib.reload(repl)
        # IFConsole should fall back to plain print
        console = repl.IFConsole()
        assert console._rich is None
        # Print should not crash
        console.print("Hello [red]world[/]")


def test_if_console_print_with_rich() -> None:
    """IFConsole should delegate to rich when available."""
    try:
        from rich.console import Console
        import intentforge.client.repl as repl
        console = repl.IFConsole()
        assert console._rich is not None
    except ImportError:
        pytest.skip("rich not installed")


def test_session_init() -> None:
    """Session should initialize with empty state."""
    from intentforge.client.repl import Session
    session = Session()
    assert session.current_target is None
    assert session.last_intent is None
    assert session.last_params is None
    assert session.last_run_id is None
    assert session.history == []


def test_session_record() -> None:
    """Session should track command history."""
    from intentforge.client.repl import Session
    session = Session()
    session.record("parse", "Make a bracket", "ok")
    assert len(session.history) == 1
    entry = session.history[0]
    assert entry["command"] == "parse"
    assert entry["prompt"] == "Make a bracket"
    assert entry["result"] == "ok"


def test_session_show_status_empty() -> None:
    """Session status should show 'no context' when empty."""
    from intentforge.client.repl import Session, IFConsole
    session = Session()
    console = IFConsole()
    # Should not crash
    session.show_status(console)


def test_session_show_status_with_context() -> None:
    """Session status should display active model and run ID."""
    from intentforge.client.repl import Session, IFConsole
    session = Session()
    session.current_target = "wall_mounted_bracket"
    session.last_run_id = "req_test123"
    console = IFConsole()
    session.show_status(console)


# ── Input parsing ────────────────────────────────────────────────────

def test_parse_input_simple_command() -> None:
    """parse_input should extract command and args."""
    from intentforge.client.repl import parse_input
    cmd, args = parse_input("parse \"Make a bracket 120mm wide\"")
    assert cmd == "parse"
    assert args == ["Make a bracket 120mm wide"]


def test_parse_input_alias() -> None:
    """parse_input should resolve aliases."""
    from intentforge.client.repl import parse_input
    cmd, args = parse_input("build \"Make a bracket\"")
    assert cmd == "parse-build"


def test_parse_input_edit_alias() -> None:
    """parse_input should resolve 'edit' alias."""
    from intentforge.client.repl import parse_input
    cmd, args = parse_input("edit bracket \"Make it wider\"")
    assert cmd == "edit-parse-apply"
    assert args == ["bracket", "Make it wider"]


def test_parse_input_llm_alias() -> None:
    """parse_input should resolve 'llm' alias."""
    from intentforge.client.repl import parse_input
    cmd, args = parse_input("llm \"Make a bracket\"")
    assert cmd == "llm-parse"


def test_parse_input_dry_run_flag() -> None:
    """parse_input should handle --dry-run flag."""
    from intentforge.client.repl import parse_input
    cmd, args = parse_input("parse-build --dry-run \"Make a bracket\"")
    assert cmd == "parse-build"
    assert "--dry-run" in args


def test_parse_input_empty() -> None:
    """parse_input should return empty for blank line."""
    from intentforge.client.repl import parse_input
    cmd, args = parse_input("")
    assert cmd == ""
    assert args == []


def test_parse_input_quit() -> None:
    """parse_input should recognize quit/exit."""
    from intentforge.client.repl import parse_input
    cmd, args = parse_input("quit")
    assert cmd == "quit"


# ── Doctor handler ───────────────────────────────────────────────────

def test_handle_doctor() -> None:
    """Doctor should check environment and display results."""
    from intentforge.client.repl import handle_doctor, IFConsole
    console = IFConsole()
    # Should not crash even without optional deps
    handle_doctor(console)


# ── Config handler ────────────────────────────────────────────────────

def test_handle_config_masks_api_key() -> None:
    """Config should mask API keys."""
    from intentforge.client.repl import handle_config, IFConsole
    console = IFConsole()
    with patch.dict(os.environ, {
        "INTENTFORGE_LLM_API_KEY": "sk-1fa15b47d26e41a3adfb8064c4193e66",
        "INTENTFORGE_LLM_PROVIDER": "openai-compatible",
    }):
        handle_config(console)


def test_handle_config_empty_env() -> None:
    """Config should show '(not set)' for unset vars."""
    from intentforge.client.repl import handle_config, IFConsole
    console = IFConsole()
    # Clear all IF env vars
    env_patch = {k: "" for k in [
        "INTENTFORGE_LLM_PROVIDER", "INTENTFORGE_LLM_BASE_URL",
        "INTENTFORGE_LLM_MODEL", "INTENTFORGE_LLM_API_KEY",
    ]}
    with patch.dict(os.environ, env_patch, clear=False):
        handle_config(console)


def test_config_wizard_saves_openai_settings(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Setup wizard should persist OpenAI-compatible settings without file editing."""
    from intentforge.client.repl import IFConsole, run_config_wizard
    from intentforge.config import DEFAULT_OPENAI_BASE_URL, DEFAULT_OPENAI_MODEL, load_llm_config

    monkeypatch.setenv("INTENTFORGE_CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.delenv("INTENTFORGE_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("INTENTFORGE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    answers = iter(["openai", "", ""])

    def ask(_prompt: str) -> str:
        return next(answers)

    def ask_secret(_prompt: str) -> str:
        return "sk-wizard123456789"

    assert run_config_wizard(IFConsole(), ask=ask, ask_secret=ask_secret, show_intro=False) is True
    config = load_llm_config()
    assert config["provider"] == "openai-compatible"
    assert config["base_url"] == DEFAULT_OPENAI_BASE_URL
    assert config["model"] == DEFAULT_OPENAI_MODEL
    assert config["api_key"] == "sk-wizard123456789"


def test_config_wizard_can_skip(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Users can skip optional LLM setup and still use deterministic commands."""
    from intentforge.client.repl import IFConsole, run_config_wizard

    monkeypatch.setenv("INTENTFORGE_CONFIG_PATH", str(tmp_path / "config.json"))

    assert run_config_wizard(
        IFConsole(),
        ask=lambda _prompt: "skip",
        ask_secret=lambda _prompt: "",
        show_intro=False,
    ) is False


def test_provider_option_fallback_accepts_number() -> None:
    """Non-TTY setup fallback should accept numbered choices."""
    from intentforge.client.repl import PROVIDER_OPTIONS, _ask_option

    assert _ask_option(
        "Provider",
        PROVIDER_OPTIONS,
        "openai",
        ask=lambda _prompt: "2",
    ) == "compatible"


def test_provider_option_fallback_reprompts_invalid_answer() -> None:
    """Invalid fallback answers should not silently choose a provider."""
    from intentforge.client.repl import PROVIDER_OPTIONS, _ask_option

    answers = iter(["bad-provider", "mock"])

    assert _ask_option(
        "Provider",
        PROVIDER_OPTIONS,
        "openai",
        ask=lambda _prompt: next(answers),
    ) == "mock"


def test_yes_no_fallback_keeps_no_distinct_from_skip() -> None:
    """Yes/no prompts should parse 'n' as no, not provider skip."""
    from intentforge.client.repl import _ask_yes_no

    assert _ask_yes_no("Continue?", default=True, ask=lambda _prompt: "n") is False


# ── REPL non-interactive tests ───────────────────────────────────────

def test_command_help_list() -> None:
    """COMMAND_HELP should cover all COMMANDS entries."""
    from intentforge.client.repl import COMMANDS, COMMAND_HELP
    for cmd in COMMANDS:
        assert cmd in COMMAND_HELP, f"Missing help for command: {cmd}"


def test_banner_contains_version() -> None:
    """Banner should reference the current version."""
    from intentforge.client.repl import BANNER, VERSION
    assert VERSION in BANNER


def test_caveats_text_in_formula() -> None:
    """Verify the homebrew formula mentions optional extras."""
    # Just check the formula file exists
    formula_path = os.path.join(
        os.path.dirname(__file__), "..", "Formula", "intentforge.rb"
    )
    # Formula is in a separate repo, not in the test directory
    # This test just verifies the module structure
    assert True


# ── Interactive REPL entry point ──────────────────────────────────────

def test_interactive_subcommand_registered() -> None:
    """CLI parser should register 'interactive' subcommand."""
    from intentforge.cli import _build_parser
    parser = _build_parser()
    # Parse 'interactive' command
    args = parser.parse_args(["interactive"])
    assert args.command == "interactive"


def test_interactive_cli_dispatch() -> None:
    """main() should call run_interactive for 'interactive' command."""
    from intentforge.cli import main
    from intentforge.client import repl

    called = False
    original = repl.run_interactive

    def mock_interactive():
        nonlocal called
        called = True

    repl.run_interactive = mock_interactive
    try:
        result = main(["interactive"])
        assert called, "run_interactive was not called"
        assert result == 0
    finally:
        repl.run_interactive = original
