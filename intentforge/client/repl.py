"""Interactive CLI client for IntentForge — Claude Code-like experience.

Provides a conversational terminal interface with:
- Rich colored output, spinners, progress bars
- Interactive prompt with auto-completion and history
- Multi-step workflow visualization
- Session context tracking
"""

from __future__ import annotations

import json
import os
import sys
import time
from getpass import getpass
from pathlib import Path
from typing import Any

from intentforge.config import (
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_OPENAI_MODEL,
    default_config_path,
    llm_configured,
    load_llm_config,
    mask_secret,
    save_llm_config,
)

# Optional imports — graceful degradation if missing
try:
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.spinner import Spinner
    from rich.table import Table
    from rich.text import Text
    from rich.markdown import Markdown
    from rich.progress import Progress, SpinnerColumn, TextColumn
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import WordCompleter
    from prompt_toolkit.history import FileHistory
    HAS_PROMPT_TOOLKIT = True
except ImportError:
    HAS_PROMPT_TOOLKIT = False


# ── Branding ──────────────────────────────────────────────────────────

APP_NAME = "IntentForge"
VERSION = "0.10.1"
BANNER = f"""
[bright_black]..........[/]              [cyan]✦[/]          [bright_black]..........................[/]
[bright_black]      ·        ░░░[/]       [cyan]▗▄▖[/]        [bright_black]        ░░░░[/]
[bright_black]   ░░░░░░░      ░░[/]      [cyan]▟██▙[/]       [bold white]IntentForge[/] [dim]v{VERSION}[/]
[bright_black]    ░░░░░░░░[/]            [cyan]██[/][white]▓▓[/]       [dim]Intent-preserving CAD[/]
[bright_black]        ░░░       ·[/]     [cyan]▝██▛[/]       [dim]Deterministic. Editable. Validated.[/]
[bright_black].....................[/]   [cyan]✧[/]      [bright_black]..............................[/]
"""

SIMPLE_BANNER = f"""IntentForge v{VERSION}
Intent-preserving deterministic CAD pipeline
"""

COMMANDS = [
    "parse", "parse-build", "edit-parse", "edit-apply",
    "edit-parse-apply", "llm-parse", "llm-parse-build",
    "llm-edit-parse", "llm-edit-apply", "demo", "benchmark",
    "doctor", "serve", "help", "quit", "exit", "status",
    "history", "clear", "config", "setup",
]

COMMAND_HELP = {
    "parse": "Parse a natural-language prompt into structured intent",
    "parse-build": "Parse + generate CAD + export STEP/STL",
    "edit-parse": "Parse an edit request for an existing model",
    "edit-apply": "Apply parsed edit + regenerate CAD",
    "edit-parse-apply": "Full edit workflow: parse edit + apply + regenerate",
    "llm-parse": "LLM-translate prompt to intent (requires LLM config)",
    "llm-parse-build": "LLM-translate + build + export",
    "llm-edit-parse": "LLM-translate edit request",
    "llm-edit-apply": "LLM-translate edit + apply + regenerate",
    "demo": "Run the full product demo",
    "benchmark": "Run benchmark suite",
    "doctor": "Check environment health",
    "serve": "Start HTTP API server",
    "status": "Show current session context and model state",
    "history": "Show command history for this session",
    "clear": "Clear screen",
    "config": "Show LLM configuration; use 'config setup' to edit",
    "setup": "Run first-time LLM configuration wizard",
    "help": "Show this help message",
    "quit": "Exit IntentForge",
    "exit": "Exit IntentForge",
}

PROVIDER_OPTIONS = [
    (
        "openai",
        "OpenAI",
        "Use api.openai.com; asks for an API key.",
    ),
    (
        "compatible",
        "OpenAI-compatible endpoint",
        "Use a custom chat-completions base URL.",
    ),
    (
        "mock",
        "Mock provider",
        "No API key; deterministic local testing.",
    ),
    (
        "skip",
        "Skip LLM setup",
        "Use deterministic CAD commands only.",
    ),
]
SELECTED_OPTION_MARKER = "●"
UNSELECTED_OPTION_MARKER = "○"
OPTION_ROW_PREFIX = "  "
OPTION_MARKER_WIDTH = 3
OPTION_LABEL_GAP = "  "
OPTION_TEXT_INDENT = " " * (len(OPTION_ROW_PREFIX) + OPTION_MARKER_WIDTH + len(OPTION_LABEL_GAP))


# ── Console wrapper (works without rich) ─────────────────────────────

class IFConsole:
    """Thin wrapper that delegates to rich.Console or falls back to plain print."""

    def __init__(self) -> None:
        if HAS_RICH:
            self._rich = Console()
        else:
            self._rich = None

    def print(self, msg: str, **kwargs: Any) -> None:
        if self._rich:
            self._rich.print(msg, **kwargs)
        else:
            # Strip rich markup for plain output
            import re
            clean = re.sub(r"\[/?[a-z _=]+\]", "", msg)
            print(clean)

    def print_panel(self, title: str, content: str, style: str = "cyan") -> None:
        if self._rich:
            self._rich.print(Panel(content, title=title, border_style=style))
        else:
            print(f"\n── {title} ──")
            print(content)
            print()

    def print_table(self, table: "Table") -> None:
        if self._rich:
            self._rich.print(table)
        else:
            # Simple text table fallback
            for row in table.rows:
                print("  ".join(str(c) for c in row))

    def print_markdown(self, text: str) -> None:
        if self._rich:
            self._rich.print(Markdown(text))
        else:
            print(text)

    def print_spinner(self, message: str, duration: float = 0) -> None:
        if HAS_RICH and duration > 0:
            with Live(Spinner("dots", text=message), console=self._rich, transient=True):
                time.sleep(duration)
        else:
            print(f"⏳ {message}")


# ── Configuration helpers ───────────────────────────────────────────

def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    return {}


def _ask_text(prompt: str, default: str = "", *, ask=input) -> str:
    suffix = f" [{default}]" if default else ""
    answer = ask(f"{prompt}{suffix}: ").strip()
    return answer or default


def _ask_yes_no(prompt: str, default: bool = True, *, ask=input) -> bool:
    if ask is input and sys.stdin.isatty() and sys.stdout.isatty():
        selected = _ask_option(
            prompt,
            [
                ("yes", "Yes", "Continue with this option."),
                ("no", "No", "Do not continue."),
            ],
            "yes" if default else "no",
            ask=ask,
        )
        return selected == "yes"

    suffix = "Y/n" if default else "y/N"
    answer = ask(f"{prompt} [{suffix}]: ").strip().lower()
    if not answer:
        return default
    return answer in {"y", "yes"}


def _normalize_option_answer(
    answer: str,
    options: list[tuple[str, str, str]],
    default: str,
) -> str | None:
    normalized = answer.strip().lower()
    if not normalized:
        return default
    if normalized.isdigit():
        index = int(normalized) - 1
        if 0 <= index < len(options):
            return options[index][0]
        return None
    option_values = {value for value, _, _ in options}
    aliases = {}
    if "skip" in option_values:
        aliases.update(
            {
                "none": "skip",
                "no": "skip",
                "openai-compatible": "compatible",
                "compatible endpoint": "compatible",
            }
        )
    if option_values == {"yes", "no"}:
        aliases.update({"y": "yes", "n": "no"})
    normalized = aliases.get(normalized, normalized)
    for value, label, _ in options:
        if normalized in {value.lower(), label.lower()}:
            return value
    return None


def _select_option_with_arrows(
    prompt: str,
    options: list[tuple[str, str, str]],
    default: str,
) -> str:
    """Select an option with prompt_toolkit-managed rendering."""

    from prompt_toolkit.application import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.styles import Style

    selected_index = next(
        (idx for idx, option in enumerate(options) if option[0] == default),
        0,
    )

    def fragments() -> list[tuple[str, str]]:
        result: list[tuple[str, str]] = [
            ("class:prompt", f"{prompt}\n"),
            ("class:hint", "Use ↑/↓ to move. Press Enter to confirm.\n\n"),
        ]
        for idx in range(len(options)):
            _, label, _ = options[idx]
            is_selected = idx == selected_index
            marker = SELECTED_OPTION_MARKER if is_selected else UNSELECTED_OPTION_MARKER
            style = "class:option.selected" if is_selected else "class:option"
            result.extend(
                [
                    (style, OPTION_ROW_PREFIX),
                    (style, f"({marker})"),
                    (style, OPTION_LABEL_GAP),
                    (style, f"{label}\n"),
                ]
            )
        result.extend(
            [
                ("", "\n"),
                ("class:description", f"{OPTION_TEXT_INDENT}{options[selected_index][2]}"),
            ]
        )
        return result

    def move_selection(next_selected: int) -> None:
        nonlocal selected_index
        if next_selected == selected_index:
            return
        selected_index = next_selected
        app.invalidate()

    kb = KeyBindings()

    @kb.add("up")
    @kb.add("k")
    @kb.add("p")
    def _move_up(event) -> None:
        move_selection((selected_index - 1) % len(options))

    @kb.add("down")
    @kb.add("j")
    @kb.add("n")
    def _move_down(event) -> None:
        move_selection((selected_index + 1) % len(options))

    @kb.add("enter")
    def _accept(event) -> None:
        event.app.exit(result=options[selected_index][0])

    @kb.add("c-c")
    def _cancel(event) -> None:
        event.app.exit(exception=KeyboardInterrupt)

    style = Style.from_dict(
        {
            "prompt": "bold",
            "hint": "ansibrightblack",
            "option": "",
            "option.selected": "bold",
            "description": "ansibrightblack",
        }
    )
    control = FormattedTextControl(fragments, focusable=True, show_cursor=False)
    app: Application[str] = Application(
        layout=Layout(Window(content=control, dont_extend_height=True)),
        key_bindings=kb,
        style=style,
        full_screen=False,
        mouse_support=False,
    )
    return app.run()


def _ask_option(
    prompt: str,
    options: list[tuple[str, str, str]],
    default: str,
    *,
    ask=input,
) -> str:
    """Choose from named options; uses arrows in TTY and text fallback elsewhere."""

    if ask is input and sys.stdin.isatty() and sys.stdout.isatty():
        try:
            return _select_option_with_arrows(prompt, options, default)
        except (ImportError, OSError):
            pass

    choices = "/".join(value for value, _, _ in options)
    while True:
        answer = _ask_text(f"{prompt} ({choices})", default, ask=ask)
        value = _normalize_option_answer(answer, options, default)
        if value is not None:
            return value
        print(f"Choose one of: {choices}, or enter 1-{len(options)}.")


def _set_current_process_llm_env(config: dict[str, str]) -> None:
    """Make saved setup usable immediately in the current REPL process."""

    os.environ["INTENTFORGE_LLM_PROVIDER"] = config["provider"]
    if config.get("base_url"):
        os.environ["INTENTFORGE_LLM_BASE_URL"] = config["base_url"]
    if config.get("model"):
        os.environ["INTENTFORGE_LLM_MODEL"] = config["model"]
    if config.get("api_key"):
        os.environ["INTENTFORGE_LLM_API_KEY"] = config["api_key"]


def run_config_wizard(
    console: IFConsole,
    *,
    ask=input,
    ask_secret=getpass,
    show_intro: bool = True,
) -> bool:
    """Run a small first-time setup wizard for optional LLM translation."""

    if show_intro:
        console.print_panel(
            "LLM Setup",
            "\n".join(
                [
                    "IntentForge deterministic CAD commands work without an LLM.",
                    "Optional LLM translation can turn flexible wording into supported intent JSON.",
                    "The LLM never generates CAD code or bypasses deterministic validation.",
                ]
            ),
        )

    provider_choice = _ask_option(
        "Provider",
        PROVIDER_OPTIONS,
        "openai",
        ask=ask,
    )
    if provider_choice == "skip":
        console.print("[dim]Skipped optional LLM setup. Deterministic commands remain available.[/]")
        return False

    if provider_choice == "mock":
        config_path = save_llm_config(provider="mock")
        _set_current_process_llm_env(
            {"provider": "mock", "base_url": "", "model": "", "api_key": ""}
        )
        console.print(f"[green]Saved mock LLM config:[/] {config_path}")
        return True

    provider = "openai-compatible"
    default_base_url = DEFAULT_OPENAI_BASE_URL if provider_choice == "openai" else ""
    base_url = _ask_text("Base URL", default_base_url, ask=ask)
    if not base_url:
        base_url = DEFAULT_OPENAI_BASE_URL
    model = _ask_text("Model", DEFAULT_OPENAI_MODEL, ask=ask)

    existing_key = os.environ.get("INTENTFORGE_LLM_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
    if existing_key and _ask_yes_no("Use existing API key from environment?", True, ask=ask):
        api_key = existing_key
    else:
        api_key = ask_secret("API key (input hidden; leave blank to skip): ").strip()
        if not api_key:
            console.print("[yellow]No API key saved. Run 'config setup' when ready.[/]")
            return False

    config_path = save_llm_config(
        provider=provider,
        base_url=base_url,
        model=model,
        api_key=api_key,
    )
    _set_current_process_llm_env(
        {
            "provider": provider,
            "base_url": base_url,
            "model": model,
            "api_key": api_key,
        }
    )
    console.print(f"[green]Saved LLM config:[/] {config_path}")
    return True


def offer_initial_setup(console: IFConsole) -> None:
    """Offer first-run setup without blocking non-interactive invocations."""

    if llm_configured() or not sys.stdin.isatty():
        return
    console.print("[dim]Optional OpenAI/LLM translation is not configured.[/]")
    if _ask_yes_no("Set it up now?", True):
        run_config_wizard(console, show_intro=False)
    else:
        console.print("[dim]You can run 'config setup' later.[/]")


# ── Session state ─────────────────────────────────────────────────────

class Session:
    """Tracks the current interactive session context."""

    def __init__(self) -> None:
        self.history: list[dict[str, Any]] = []
        self.current_target: str | None = None
        self.last_intent: dict[str, Any] | None = None
        self.last_params: dict[str, Any] | None = None
        self.last_run_id: str | None = None
        self.output_dir: Path = Path(os.environ.get(
            "INTENTFORGE_OUTPUT_DIR", "output"
        ))

    def record(self, command: str, prompt: str, result: Any) -> None:
        self.history.append({
            "command": command,
            "prompt": prompt,
            "result": result,
            "timestamp": time.strftime("%H:%M:%S"),
        })

    def show_status(self, console: IFConsole) -> None:
        lines = []
        if self.current_target:
            lines.append(f"  Active model: [bold]{self.current_target}[/]")
        if self.last_run_id:
            lines.append(f"  Last run ID:   {self.last_run_id}")
        if self.last_intent:
            obj_type = self.last_intent.get("object_type", "?")
            lines.append(f"  Last intent:   {obj_type}")
        if self.last_params:
            param_keys = list(self.last_params.get("parameters", {}).keys())[:5]
            lines.append(f"  Last params:   {', '.join(param_keys)}...")
        if not lines:
            lines.append("  [dim]No active context — start with a parse or build command[/]")

        console.print_panel("Session Status", "\n".join(lines))


# ── Command handlers ──────────────────────────────────────────────────

def handle_parse(console: IFConsole, session: Session, prompt_text: str) -> None:
    """Run deterministic parse workflow."""
    from intentforge.workflows import parse_prompt_workflow

    console.print_spinner("Parsing intent...", 0.1)
    try:
        result = parse_prompt_workflow(prompt_text)
        if not result.get("ok"):
            _display_error(console, result)
            session.record("parse", prompt_text, f"error: {result.get('message') or result.get('error_type')}")
            return

        intent = result["intent"]
        session.current_target = result.get("object_type") or intent.get("family")
        session.last_intent = intent
        session.last_run_id = result.get("run_id") or result.get("request_id")
        session.record("parse", prompt_text, "ok")

        _display_intent(console, intent)
    except Exception as e:
        console.print(f"[red]Error:[/] {e}")
        session.record("parse", prompt_text, f"error: {e}")


def handle_parse_build(console: IFConsole, session: Session, prompt_text: str,
                       dry_run: bool = False) -> None:
    """Run parse + build workflow."""
    from intentforge.workflows import parse_build_workflow

    steps = ["Parsing intent", "Generating parameters", "Planning features"]
    if not dry_run:
        steps += ["Building CAD model", "Exporting STEP/STL", "Validating geometry"]

    console.print_spinner("Starting parse-build workflow...", 0.1)

    try:
        result = parse_build_workflow(prompt_text, session.output_dir, dry_run=dry_run)
        if not result.get("ok") and "validation_report" not in result:
            _display_error(console, result)
            session.record("parse-build", prompt_text, f"error: {result.get('message') or result.get('error_type')}")
            return

        intent = result["intent"]
        params = result["parameters"]
        session.current_target = result.get("object_type") or intent.get("family")
        session.last_intent = intent
        session.last_params = params
        session.last_run_id = result.get("run_id") or result.get("request_id")
        session.record("parse-build", prompt_text, "ok")

        _display_intent(console, intent)
        _display_params(console, params)
        _display_build_result(console, result, dry_run)
    except Exception as e:
        console.print(f"[red]Error:[/] {e}")
        session.record("parse-build", prompt_text, f"error: {e}")


def handle_edit(console: IFConsole, session: Session, target: str,
                edit_text: str) -> None:
    """Run edit-parse-apply workflow."""
    from intentforge.workflows import edit_parse_apply_workflow

    if not session.current_target and not target:
        console.print("[yellow]No active model. Specify a target or run parse-build first.[/]")
        return

    effective_target = target or session.current_target or "bracket"
    console.print_spinner(f"Editing {effective_target}...", 0.1)

    try:
        result = edit_parse_apply_workflow(effective_target, edit_text, session.output_dir)
        if not result.get("ok") and not result.get("accepted"):
            _display_edit_result(console, result)
            session.record("edit-parse-apply", edit_text, f"error: {result.get('message') or result.get('error_type')}")
            return

        session.current_target = result.get("object_type") or effective_target
        edit_report = result.get("edit_report", {})
        metadata = edit_report.get("metadata", {}) if isinstance(edit_report, dict) else {}
        updated_params = metadata.get("updated_parameter_table")
        if updated_params:
            session.last_params = updated_params
        session.last_run_id = result.get("run_id") or result.get("request_id")
        session.record("edit-parse-apply", edit_text, "ok")

        _display_edit_result(console, result)
    except Exception as e:
        console.print(f"[red]Error:[/] {e}")
        session.record("edit-parse-apply", edit_text, f"error: {e}")


def handle_llm_parse(console: IFConsole, session: Session, prompt_text: str) -> None:
    """Run LLM translation + deterministic parse workflow."""
    from intentforge.llm import load_provider_from_env, translate_prompt_to_intent

    try:
        provider = load_provider_from_env()
    except Exception as e:
        console.print(f"[yellow]LLM provider is not usable:[/] {e}")
        return
    if provider is None:
        console.print("[yellow]No LLM provider configured. Run 'config setup' or set OPENAI_API_KEY.[/]")
        return

    console.print_spinner("Translating via LLM...", 0.5)

    try:
        result = translate_prompt_to_intent(prompt_text, provider)
        if not result.get("ok"):
            _display_error(console, result, label="LLM Error")
            session.record("llm-parse", prompt_text, f"error: {result.get('message') or result.get('error_type')}")
            return

        intent = result["intent"]
        session.current_target = result.get("object_type") or intent.get("family")
        session.last_intent = intent
        session.last_run_id = result.get("run_id") or result.get("request_id")
        session.record("llm-parse", prompt_text, "ok")

        _display_intent(console, intent)
        console.print("[green]✓ LLM translation successful[/]")
    except Exception as e:
        console.print(f"[red]LLM Error:[/] {e}")
        session.record("llm-parse", prompt_text, f"error: {e}")


def handle_llm_parse_build(console: IFConsole, session: Session,
                           prompt_text: str, dry_run: bool = False) -> None:
    """Run LLM translation + parse + build workflow."""
    from intentforge.llm import load_provider_from_env, translate_prompt_to_build

    try:
        provider = load_provider_from_env()
    except Exception as e:
        console.print(f"[yellow]LLM provider is not usable:[/] {e}")
        return
    if provider is None:
        console.print("[yellow]No LLM provider configured. Run 'config setup' or set OPENAI_API_KEY.[/]")
        return

    console.print_spinner("Translating via LLM + building...", 0.5)

    try:
        result = translate_prompt_to_build(prompt_text, provider, session.output_dir, dry_run=dry_run)
        if not result.get("ok") and "validation_report" not in result:
            _display_error(console, result, label="LLM Build Error")
            session.record("llm-parse-build", prompt_text, f"error: {result.get('message') or result.get('error_type')}")
            return

        intent = result["intent"]
        params = result["parameters"]
        session.current_target = result.get("object_type") or intent.get("family")
        session.last_intent = intent
        session.last_params = params
        session.last_run_id = result.get("run_id") or result.get("request_id")
        session.record("llm-parse-build", prompt_text, "ok")

        _display_intent(console, intent)
        _display_params(console, params)
        _display_build_result(console, result, dry_run)
        console.print("[green]✓ LLM translation + build successful[/]")
    except Exception as e:
        console.print(f"[red]LLM Build Error:[/] {e}")
        session.record("llm-parse-build", prompt_text, f"error: {e}")


def handle_doctor(console: IFConsole) -> None:
    """Check environment health."""
    checks = []

    # Check core deps
    try:
        import pydantic
        checks.append(("pydantic", True, pydantic.__version__))
    except ImportError:
        checks.append(("pydantic", False, "missing"))

    try:
        import yaml
        checks.append(("PyYAML", True, yaml.__version__))
    except ImportError:
        checks.append(("PyYAML", False, "missing"))

    # Check optional deps
    try:
        import cadquery
        checks.append(("CadQuery", True, cadquery.__version__))
    except ImportError:
        checks.append(("CadQuery", False, "install with: pip install -e '.[cad]'"))

    try:
        import fastapi
        checks.append(("FastAPI", True, fastapi.__version__))
    except ImportError:
        checks.append(("FastAPI", False, "install with: pip install -e '.[api]'"))

    try:
        import mcp
        checks.append(("MCP", True, "available"))
    except ImportError:
        checks.append(("MCP", False, "install with: pip install -e '.[mcp]'"))

    # Check LLM config
    llm_provider = load_llm_config()["provider"]
    if llm_provider:
        checks.append(("LLM Provider", True, llm_provider))
    else:
        checks.append(("LLM Provider", False, "not configured"))

    # Check rich
    checks.append(("Rich (UI)", HAS_RICH, "installed" if HAS_RICH else "missing"))

    checks.append(("prompt_toolkit", HAS_PROMPT_TOOLKIT,
                    "installed" if HAS_PROMPT_TOOLKIT else "missing"))

    if HAS_RICH:
        table = Table(title="Environment Health Check", show_header=True)
        table.add_column("Component", style="bold")
        table.add_column("Status")
        table.add_column("Detail")

        for name, ok, detail in checks:
            status = "[green]✓[/]" if ok else "[red]✗[/]"
            style = "green" if ok else "red"
            table.add_row(name, status, detail, style=style)
        console.print_table(table)
    else:
        for name, ok, detail in checks:
            status = "✓" if ok else "✗"
            print(f"  {status} {name}: {detail}")


def handle_config(console: IFConsole) -> None:
    """Show current LLM configuration."""
    config = load_llm_config()
    lines = [
        f"  Config file = {default_config_path()}",
        f"  LLM configured = {str(llm_configured()).lower()}",
        f"  Provider = {config['provider'] or '[dim](not set)[/]'}",
        f"  Base URL = {config['base_url'] or '[dim](not set)[/]'}",
        f"  Model = {config['model'] or '[dim](not set)[/]'}",
        f"  API key = {mask_secret(config['api_key']) if config['api_key'] else '[dim](not set)[/]'}",
        f"  Output dir = {os.environ.get('INTENTFORGE_OUTPUT_DIR', 'output')}",
        f"  API token = {mask_secret(os.environ.get('INTENTFORGE_API_TOKEN', '')) if os.environ.get('INTENTFORGE_API_TOKEN') else '[dim](not set)[/]'}",
        "",
        "Run 'config setup' to configure or update the optional LLM provider.",
    ]

    console.print_panel("Configuration", "\n".join(lines))


def handle_history(console: IFConsole, session: Session) -> None:
    """Show session command history."""
    if not session.history:
        console.print("[dim]No commands in this session yet.[/]")
        return

    if HAS_RICH:
        table = Table(title="Session History", show_header=True)
        table.add_column("Time", style="dim")
        table.add_column("Command", style="bold")
        table.add_column("Prompt", max_width=40)
        table.add_column("Result")

        for entry in session.history:
            result_style = "green" if str(entry["result"]) == "ok" else "red"
            prompt_display = entry["prompt"][:40] + "..." if len(entry["prompt"]) > 40 else entry["prompt"]
            table.add_row(
                entry["timestamp"],
                entry["command"],
                prompt_display,
                str(entry["result"]),
                style=result_style,
            )
        console.print_table(table)
    else:
        for entry in session.history:
            print(f"  [{entry['timestamp']}] {entry['command']}: {entry['prompt'][:40]}")


# ── Display helpers ───────────────────────────────────────────────────

def _display_error(console: IFConsole, result: dict[str, Any], label: str = "Error") -> None:
    error = result.get("error") or {}
    message = (
        error.get("message")
        or result.get("message")
        or result.get("error_type")
        or "Command failed."
    )
    lines = [f"[red]{message}[/]"]
    error_type = error.get("error_type") or result.get("error_type")
    if error_type:
        lines.append(f"Error type: {error_type}")
    if error.get("suggested_action"):
        lines.append(f"Suggested action: {error['suggested_action']}")
    if result.get("request_id"):
        lines.append(f"Request ID: {result['request_id']}")
    console.print_panel(label, "\n".join(lines), style="red")


def _display_intent(console: IFConsole, intent: Any) -> None:
    """Pretty-print parsed intent."""
    data = _as_dict(intent)

    obj_type = data.get("object_type") or data.get("family") or "?"
    units = data.get("units", "mm")
    assumptions = data.get("assumptions", [])
    unknowns = data.get("unknowns", [])
    warnings = data.get("warnings", [])
    feature_flags = data.get("feature_flags", {})

    lines = [f"[bold green]Parsed Intent:[/] [white]{obj_type}[/] [dim]({units})[/]"]

    if feature_flags:
        lines.append("\n[bold]Feature Flags:[/]")
        for flag_name, flag_data in feature_flags.items():
            if isinstance(flag_data, dict):
                state = flag_data.get("state", "?")
                reason = flag_data.get("reason", "")
                state_color = "green" if state == "requested_by_user" else "yellow" if state == "defaulted_by_system" else "dim"
                lines.append(f"  [{state_color}]•[/] {flag_name}: [{state_color}]{state}[/] [dim]({reason})[/]")
            else:
                lines.append(f"  • {flag_name}: {flag_data}")

    if assumptions:
        lines.append("\n[bold]Assumptions:[/]")
        for a in assumptions[:5]:
            lines.append(f"  [dim]•[/] {a}")
        if len(assumptions) > 5:
            lines.append(f"  [dim]• ...and {len(assumptions) - 5} more[/]")

    if unknowns:
        lines.append("\n[yellow]Unknowns:[/]")
        for u in unknowns[:5]:
            lines.append(f"  [yellow]•[/] {u}")

    if warnings:
        lines.append("\n[red]Warnings:[/]")
        for w in warnings:
            lines.append(f"  [red]•[/] {w}")

    console.print_panel("Intent", "\n".join(lines))


def _display_params(console: IFConsole, params: Any) -> None:
    """Pretty-print parameter table."""
    data = _as_dict(params)
    parameters = data.get("parameters", [])

    if HAS_RICH:
        table = Table(title="Parameters", show_header=True)
        table.add_column("Name", style="bold")
        table.add_column("Value")
        table.add_column("Unit", style="dim")
        table.add_column("Source")
        table.add_column("Locked")

        for name, pdata in _iter_parameters(parameters):
            val = pdata.get("value", "?")
            unit = pdata.get("unit", "")
            source = pdata.get("source", "?")
            locked = pdata.get("locked", False)
            lock_icon = "[red]🔒[/]" if locked else "[dim]—[/]"
            table.add_row(name, str(val), unit or "", source, lock_icon)
        console.print_table(table)
    else:
        for name, pdata in _iter_parameters(parameters):
            val = pdata.get("value", "?")
            unit = pdata.get("unit", "")
            source = pdata.get("source", "?")
            print(f"  {name} = {val} {unit} ({source})")


def _iter_parameters(parameters: Any) -> list[tuple[str, dict[str, Any]]]:
    if isinstance(parameters, dict):
        return [
            (name, pdata)
            for name, pdata in parameters.items()
            if isinstance(pdata, dict)
        ]
    if isinstance(parameters, list):
        rows = []
        for pdata in parameters:
            if isinstance(pdata, dict):
                rows.append((str(pdata.get("name", "?")), pdata))
        return rows
    return []


def _display_build_result(console: IFConsole, result: Any, dry_run: bool) -> None:
    """Pretty-print build result summary."""
    if dry_run:
        console.print("[yellow]Dry run — no STEP/STL files exported[/]")
        return

    data = _as_dict(result)
    lines = []
    latest_outputs = data.get("latest_outputs", {})
    if data.get("cad_exported"):
        lines.append("[green]✓ STEP/STL files exported[/]")
        if latest_outputs.get("step"):
            lines.append(f"[green]STEP:[/] {latest_outputs['step']}")
        if latest_outputs.get("stl"):
            lines.append(f"[green]STL:[/]  {latest_outputs['stl']}")
    else:
        lines.append("[dim]No CAD export (CadQuery not available)[/]")

    validation_report = data.get("validation_report") or {}
    checks = validation_report.get("checks", []) if isinstance(validation_report, dict) else []
    if checks:
        passed = sum(1 for c in checks if isinstance(c, dict) and c.get("status") in {"pass", "warning"})
        total = len(checks)
        lines.append(f"[bold]Validation:[/] {passed}/{total} checks passed")
        if passed < total:
            failed = [c for c in checks if isinstance(c, dict) and c.get("status") == "fail"]
            for c in failed[:3]:
                lines.append(f"  [red]✗[/] {c.get('name', '?')}: {c.get('message', 'failed')}")

    console.print_panel("Build Result", "\n".join(lines))


def _display_edit_result(console: IFConsole, result: Any) -> None:
    """Pretty-print edit result."""
    data = _as_dict(result)
    lines = []

    if not data.get("accepted", data.get("ok", False)):
        lines.append(f"[red]{data.get('message', 'Edit was rejected.')}[/]")

    er = data.get("edit_report")
    if isinstance(er, dict):
        changes = er.get("changed_parameters", [])
        preserved = er.get("preserved_parameters", [])
        lines.append(f"[bold]Changes:[/] {len(changes)} parameter(s) modified")
        for c in changes[:5]:
            lines.append(f"  [cyan]→[/] {c}")
        lines.append(f"[bold]Preserved:[/] {len(preserved)} parameter(s) unchanged")
        for p in preserved[:3]:
            lines.append(f"  [green]✓[/] {p}")

    if data.get("object_type"):
        lines.append(f"\n[bold]Object type:[/] {data['object_type']}")
    if data.get("persistent_output_dir"):
        lines.append(f"[bold]Output:[/] {data['persistent_output_dir']}")

    console.print_panel("Edit Result", "\n".join(lines) or "No edit details available.")


# ── Input parser ──────────────────────────────────────────────────────

def parse_input(line: str) -> tuple[str, list[str]]:
    """Parse a command line into (command, args).

    Supports:
      parse-build "Make a bracket..."
      edit bracket "Make it wider"
      llm-parse-build --dry-run "..."
    """
    parts = line.strip().split()
    if not parts:
        return ("", [])

    cmd = parts[0].lower()

    # Normalize aliases
    cmd_aliases = {
        "build": "parse-build",
        "edit": "edit-parse-apply",
        "llm": "llm-parse",
        "llm-build": "llm-parse-build",
        "llm-edit": "llm-edit-apply",
    }
    cmd = cmd_aliases.get(cmd, cmd)

    # Collect args (handle quoted strings)
    args = []
    current = ""
    in_quote = False
    rest = " ".join(parts[1:])

    for char in rest:
        if char == '"':
            in_quote = not in_quote
        elif char == ' ' and not in_quote:
            if current:
                args.append(current)
                current = ""
        else:
            current += char
    if current:
        args.append(current)

    return (cmd, args)


# ── Main REPL ─────────────────────────────────────────────────────────

def run_interactive() -> None:
    """Run the interactive IntentForge REPL."""
    console = IFConsole()
    session = Session()

    # Banner
    if HAS_RICH:
        console._rich.print(BANNER)
    else:
        print(SIMPLE_BANNER)

    # LLM status hint
    offer_initial_setup(console)
    llm_config = load_llm_config()
    llm_provider = llm_config["provider"]
    if llm_provider:
        console.print(f"[dim]LLM: {llm_provider} ({llm_config['model'] or 'no model'})[/]")
    else:
        console.print("[dim]LLM: not configured (core features still work)[/]")

    console.print("[dim]Type 'help' for commands, 'quit' to exit.[/]\n")

    # Set up prompt session
    history_file = Path.home() / ".intentforge" / "cli_history"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    if HAS_PROMPT_TOOLKIT and sys.stdin.isatty():
        completer = WordCompleter(COMMANDS, ignore_case=True)
        psession = PromptSession(
            history=FileHistory(str(history_file)),
            completer=completer,
            message="IF> ",
        )
    else:
        psession = None

    while True:
        try:
            if psession:
                line = psession.prompt()
            else:
                line = input("IF> ")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Bye.[/]")
            break

        if not line.strip():
            continue

        cmd, args = parse_input(line)

        # ── Handle commands ──
        if cmd in ("quit", "exit"):
            console.print("[dim]Bye.[/]")
            break

        elif cmd == "help":
            if HAS_RICH:
                table = Table(title="Commands", show_header=True)
                table.add_column("Command", style="bold cyan")
                table.add_column("Description")
                for c in COMMANDS:
                    if c in COMMAND_HELP:
                        table.add_row(c, COMMAND_HELP[c])
                console.print_table(table)
            else:
                for c in COMMANDS:
                    if c in COMMAND_HELP:
                        print(f"  {c}: {COMMAND_HELP[c]}")

        elif cmd == "clear":
            if HAS_RICH:
                console._rich.clear()
            else:
                print("\033[2J\033[H")

        elif cmd == "status":
            session.show_status(console)

        elif cmd == "history":
            handle_history(console, session)

        elif cmd == "doctor":
            handle_doctor(console)

        elif cmd == "config":
            if args and args[0] in {"setup", "init", "edit"}:
                run_config_wizard(console)
            else:
                handle_config(console)

        elif cmd == "setup":
            run_config_wizard(console)

        elif cmd == "parse":
            if not args:
                console.print("[yellow]Usage: parse \"your prompt here\"[/]")
                continue
            prompt_text = " ".join(args)
            handle_parse(console, session, prompt_text)

        elif cmd == "parse-build":
            if not args:
                console.print("[yellow]Usage: parse-build [--dry-run] \"your prompt here\"[/]")
                continue
            dry_run = "--dry-run" in args
            filtered_args = [a for a in args if a != "--dry-run"]
            prompt_text = " ".join(filtered_args)
            handle_parse_build(console, session, prompt_text, dry_run=dry_run)

        elif cmd in ("edit-parse-apply", "edit"):
            if len(args) < 2:
                console.print("[yellow]Usage: edit-parse-apply <target> \"your edit request\"[/]")
                continue
            target = args[0]
            edit_text = " ".join(args[1:])
            handle_edit(console, session, target, edit_text)

        elif cmd == "llm-parse":
            if not args:
                console.print("[yellow]Usage: llm-parse \"your prompt here\"[/]")
                continue
            prompt_text = " ".join(args)
            handle_llm_parse(console, session, prompt_text)

        elif cmd in ("llm-parse-build", "llm-build"):
            if not args:
                console.print("[yellow]Usage: llm-parse-build [--dry-run] \"your prompt here\"[/]")
                continue
            dry_run = "--dry-run" in args
            filtered_args = [a for a in args if a != "--dry-run"]
            prompt_text = " ".join(filtered_args)
            handle_llm_parse_build(console, session, prompt_text, dry_run=dry_run)

        elif cmd == "demo":
            from intentforge.demo_runner import run_demo
            console.print_spinner("Running demo...", 0.1)
            try:
                run_demo()
                console.print("[green]✓ Demo complete[/]")
            except Exception as e:
                console.print(f"[red]Demo error:[/] {e}")

        elif cmd == "benchmark":
            from benchmark.run_benchmark import run_benchmark
            console.print_spinner("Running benchmark...", 0.1)
            try:
                run_benchmark()
                console.print("[green]✓ Benchmark complete[/]")
            except Exception as e:
                console.print(f"[red]Benchmark error:[/] {e}")

        elif cmd == "serve":
            from intentforge.api.server import serve
            console.print("[cyan]Starting API server...[/]")
            try:
                serve()
            except Exception as e:
                console.print(f"[red]Server error:[/] {e}")

        else:
            console.print(f"[yellow]Unknown command:[/] {cmd}. Type 'help' for available commands.")


def main() -> None:
    """Entry point for the interactive CLI."""
    run_interactive()


if __name__ == "__main__":
    main()
