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
from pathlib import Path
from typing import Any

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
VERSION = "0.10.0"
BANNER = f"""
[cyan]╔══════════════════════════════════════════════════╗[/]
[cyan]║[/]  [bold white]IntentForge[/] [dim]v{VERSION}[/]                              [cyan]║[/]
[cyan]║[/]  [dim]Intent-preserving deterministic CAD pipeline[/]    [cyan]║[/]
[cyan]╚══════════════════════════════════════════════════╝[/]
"""

SIMPLE_BANNER = f"""IntentForge v{VERSION}
Intent-preserving deterministic CAD pipeline
"""

COMMANDS = [
    "parse", "parse-build", "edit-parse", "edit-apply",
    "edit-parse-apply", "llm-parse", "llm-parse-build",
    "llm-edit-parse", "llm-edit-apply", "demo", "benchmark",
    "doctor", "serve", "help", "quit", "exit", "status",
    "history", "clear", "config",
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
    "config": "Show / edit LLM configuration",
    "help": "Show this help message",
    "quit": "Exit IntentForge",
    "exit": "Exit IntentForge",
}


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
    from intentforge.schemas import IntentSpec

    console.print_spinner("Parsing intent...", 0.1)
    try:
        result = parse_prompt_workflow(prompt_text)
        intent = result.intent
        session.current_target = intent.object_type
        session.last_intent = intent.model_dump() if hasattr(intent, "model_dump") else intent.dict()
        session.last_run_id = result.run_id
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
        result = parse_build_workflow(prompt_text, dry_run=dry_run)
        intent = result.intent
        session.current_target = intent.object_type
        session.last_intent = intent.model_dump() if hasattr(intent, "model_dump") else intent.dict()
        session.last_params = result.params.model_dump() if hasattr(result.params, "model_dump") else result.params.dict()
        session.last_run_id = result.run_id
        session.record("parse-build", prompt_text, "ok")

        _display_intent(console, intent)
        _display_params(console, result.params)
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
        result = edit_parse_apply_workflow(effective_target, edit_text)
        session.current_target = effective_target
        session.last_intent = result.updated_intent.model_dump() if hasattr(result.updated_intent, "model_dump") else result.updated_intent.dict()
        session.last_params = result.updated_params.model_dump() if hasattr(result.updated_params, "model_dump") else result.updated_params.dict()
        session.last_run_id = result.run_id
        session.record("edit-parse-apply", edit_text, "ok")

        _display_edit_result(console, result)
    except Exception as e:
        console.print(f"[red]Error:[/] {e}")
        session.record("edit-parse-apply", edit_text, f"error: {e}")


def handle_llm_parse(console: IFConsole, session: Session, prompt_text: str) -> None:
    """Run LLM translation + deterministic parse workflow."""
    from intentforge.llm import load_provider_from_env, translate_prompt_to_intent

    provider = load_provider_from_env()
    if provider is None:
        console.print("[yellow]No LLM provider configured. Set INTENTFORGE_LLM_* env vars or run 'config'.[/]")
        return

    console.print_spinner("Translating via LLM...", 0.5)

    try:
        result = translate_prompt_to_intent(provider, prompt_text)
        intent = result.intent
        session.current_target = intent.object_type
        session.last_intent = intent.model_dump() if hasattr(intent, "model_dump") else intent.dict()
        session.last_run_id = result.run_id
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

    provider = load_provider_from_env()
    if provider is None:
        console.print("[yellow]No LLM provider configured.[/]")
        return

    console.print_spinner("Translating via LLM + building...", 0.5)

    try:
        result = translate_prompt_to_build(provider, prompt_text, dry_run=dry_run)
        intent = result.intent
        session.current_target = intent.object_type
        session.last_intent = intent.model_dump() if hasattr(intent, "model_dump") else intent.dict()
        session.last_params = result.params.model_dump() if hasattr(result.params, "model_dump") else result.params.dict()
        session.last_run_id = result.run_id
        session.record("llm-parse-build", prompt_text, "ok")

        _display_intent(console, intent)
        _display_params(console, result.params)
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
    llm_provider = os.environ.get("INTENTFORGE_LLM_PROVIDER", "")
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
    keys = [
        "INTENTFORGE_LLM_PROVIDER",
        "INTENTFORGE_LLM_BASE_URL",
        "INTENTFORGE_LLM_MODEL",
        "INTENTFORGE_LLM_API_KEY",
        "INTENTFORGE_OUTPUT_DIR",
        "INTENTFORGE_API_HOST",
        "INTENTFORGE_API_PORT",
        "INTENTFORGE_API_TOKEN",
    ]
    lines = []
    for key in keys:
        val = os.environ.get(key, "")
        # Mask API key
        if "API_KEY" in key and val:
            masked = val[:6] + "..." + val[-4:] if len(val) > 10 else "***"
            lines.append(f"  {key} = {masked}")
        elif val:
            lines.append(f"  {key} = {val}")
        else:
            lines.append(f"  {key} = [dim](not set)[/]")

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

def _display_intent(console: IFConsole, intent: Any) -> None:
    """Pretty-print parsed intent."""
    data = intent.model_dump() if hasattr(intent, "model_dump") else intent.dict()

    obj_type = data.get("object_type", "?")
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
    data = params.model_dump() if hasattr(params, "model_dump") else params.dict()
    parameters = data.get("parameters", {})

    if HAS_RICH:
        table = Table(title="Parameters", show_header=True)
        table.add_column("Name", style="bold")
        table.add_column("Value")
        table.add_column("Unit", style="dim")
        table.add_column("Source")
        table.add_column("Locked")

        for name, pdata in parameters.items():
            if isinstance(pdata, dict):
                val = pdata.get("value", "?")
                unit = pdata.get("unit", "")
                source = pdata.get("source", "?")
                locked = pdata.get("locked", False)
                lock_icon = "[red]🔒[/]" if locked else "[dim]—[/]"
                source_color = "cyan" if source == "user_specified" else "yellow" if source == "default" else "dim"
                table.add_row(name, str(val), unit, source, lock_icon)
        console.print_table(table)
    else:
        for name, pdata in parameters.items():
            if isinstance(pdata, dict):
                val = pdata.get("value", "?")
                unit = pdata.get("unit", "")
                source = pdata.get("source", "?")
                print(f"  {name} = {val} {unit} ({source})")


def _display_build_result(console: IFConsole, result: Any, dry_run: bool) -> None:
    """Pretty-print build result summary."""
    if dry_run:
        console.print("[yellow]Dry run — no STEP/STL files exported[/]")
        return

    lines = []
    if hasattr(result, "cad_exported") and result.cad_exported:
        lines.append("[green]✓ STEP/STL files exported[/]")
    elif hasattr(result, "step_path") and result.step_path:
        lines.append(f"[green]✓ STEP:[/] {result.step_path}")
        if hasattr(result, "stl_path") and result.stl_path:
            lines.append(f"[green]✓ STL:[/]  {result.stl_path}")
    else:
        lines.append("[dim]No CAD export (CadQuery not available)[/]")

    if hasattr(result, "validation_report"):
        vr = result.validation_report
        if vr and hasattr(vr, "checks"):
            passed = sum(1 for c in vr.checks if c.passed)
            total = len(vr.checks)
            lines.append(f"[bold]Validation:[/] {passed}/{total} checks passed")
            if passed < total:
                failed = [c for c in vr.checks if not c.passed]
                for c in failed[:3]:
                    lines.append(f"  [red]✗[/] {c.name}: expected {c.expected}, got {c.actual}")

    console.print_panel("Build Result", "\n".join(lines))


def _display_edit_result(console: IFConsole, result: Any) -> None:
    """Pretty-print edit result."""
    lines = []

    if hasattr(result, "edit_report"):
        er = result.edit_report
        if isinstance(er, dict):
            changes = er.get("changes", [])
            preserved = er.get("preserved", [])
            lines.append(f"[bold]Changes:[/] {len(changes)} parameter(s) modified")
            for c in changes[:5]:
                lines.append(f"  [cyan]→[/] {c}")
            lines.append(f"[bold]Preserved:[/] {len(preserved)} parameter(s) unchanged")
            for p in preserved[:3]:
                lines.append(f"  [green]✓[/] {p}")

    if hasattr(result, "updated_intent"):
        lines.append(f"\n[bold]Updated intent:[/] {result.updated_intent.object_type}")

    console.print_panel("Edit Result", "\n".join(lines))


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
    llm_provider = os.environ.get("INTENTFORGE_LLM_PROVIDER", "")
    if llm_provider:
        console.print(f"[dim]LLM: {llm_provider} ({os.environ.get('INTENTFORGE_LLM_MODEL', '?')})[/]")
    else:
        console.print("[dim]LLM: not configured (core features still work)[/]")

    console.print("[dim]Type 'help' for commands, 'quit' to exit.[/]\n")

    # Set up prompt session
    history_file = Path.home() / ".intentforge" / "cli_history"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    if HAS_PROMPT_TOOLKIT:
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
            handle_config(console)

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
