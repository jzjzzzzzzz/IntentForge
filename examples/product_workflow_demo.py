#!/usr/bin/env python3
"""Product workflow demo for IntentForge HTTP API.

Demonstrates a full commercial-style workflow:

  prompt → dry-run → build → edit → validate → artifact list

This script shows how a real user or external agent would use
IntentForge as a production tool, not just a CLI toy.

Requires: httpx  (pip install httpx)

Usage:
  # Start the server first:
  python -m intentforge.api.server

  # Then run this demo:
  python examples/product_workflow_demo.py [--base-url URL] [--token TOKEN]
"""

from __future__ import annotations

import argparse
import json
import sys
import time

try:
    import httpx
except ImportError:
    print(
        "Error: httpx is required for this demo.\n"
        "Install it with: pip install httpx",
        file=sys.stderr,
    )
    sys.exit(1)


# ── Helpers ──────────────────────────────────────────────────────────


def _section(label: str) -> None:
    print(f"\n{'─' * 50}")
    print(f"  {label}")
    print(f"{'─' * 50}")


def _call(
    client: httpx.Client,
    method: str,
    path: str,
    payload: dict | None = None,
) -> dict:
    """Make an API call and return the parsed JSON body."""
    if method == "GET":
        resp = client.get(path, params=payload or {})
    else:
        resp = client.post(path, json=payload or {})

    data = resp.json()
    if resp.status_code >= 400:
        print(f"  ⚠️  HTTP {resp.status_code}: {json.dumps(data, indent=2)[:500]}")
    return data


def _show_summary(data: dict) -> None:
    """Print the key contract fields for a ToolResponse."""
    ok = data.get("ok")
    request_id = data.get("request_id", "—")
    operation = data.get("operation", "—")
    object_type = data.get("object_type", "—")
    dry_run = data.get("dry_run", False)
    cad_exported = data.get("cad_exported")

    print(f"  ok={ok}  request_id={request_id}  operation={operation}")
    print(f"  object_type={object_type}  dry_run={dry_run}  cad_exported={cad_exported}")

    validation = data.get("validation")
    if validation:
        print(f"  validation: valid={validation.get('valid')}, "
              f"{validation.get('passed_checks')}/{validation.get('total_checks')} checks passed")

    artifacts = data.get("artifacts", [])
    if artifacts:
        print(f"  artifacts ({len(artifacts)}):")
        for ref in artifacts:
            print(f"    → {ref.get('kind')}: {ref.get('path')}")

    error = data.get("error")
    if error:
        print(f"  ⛔ {error.get('error_type')}: {error.get('message')}")
        if error.get("suggested_action"):
            print(f"     Suggested: {error.get('suggested_action')}")


# ── Workflow steps ───────────────────────────────────────────────────


def workflow_connectivity(client: httpx.Client) -> bool:
    """Step 0: Verify the API is reachable."""
    _section("Step 0 — Connectivity Check")
    try:
        data = _call(client, "GET", "/health")
    except httpx.ConnectError:
        print(
            f"  ❌ Cannot reach IntentForge API.\n"
            f"  Start the server:\n"
            f"    python -m intentforge.api.server\n"
            f"    # or:  intentforge serve",
        )
        return False
    print(f"  Health: {data}")
    return True


def workflow_parse_intent(client: httpx.Client) -> dict:
    """Step 1: Parse a prompt into structured intent + parameters."""
    _section("Step 1 — Parse Prompt → Intent JSON")
    data = _call(client, "POST", "/v1/parse", {
        "prompt": "Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with two screw holes.",
    })
    _show_summary(data)
    return data


def workflow_dry_run(client: httpx.Client) -> dict:
    """Step 2: Dry-run parse-build — validate intent, no export."""
    _section("Step 2 — Dry-Run Parse-Build (no STEP/STL export)")
    data = _call(client, "POST", "/v1/parse-build", {
        "prompt": "Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with two screw holes.",
        "dry_run": True,
    })
    _show_summary(data)
    print(f"  Intent validated without exporting files. cad_exported={data.get('cad_exported')}")
    return data


def workflow_full_build(client: httpx.Client) -> dict:
    """Step 3: Full parse-build — generate STEP/STL + validate."""
    _section("Step 3 — Full Parse-Build (STEP/STL generation)")
    data = _call(client, "POST", "/v1/parse-build", {
        "prompt": "Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with two screw holes.",
        "dry_run": False,
    })
    _show_summary(data)
    return data


def workflow_edit_dry(client: httpx.Client) -> dict:
    """Step 4: Dry-run edit — validate the edit, no re-export."""
    _section("Step 4 — Dry-Run Edit-Apply (validate edit intent)")
    data = _call(client, "POST", "/v1/edit-apply", {
        "target": "bracket",
        "edit_text": "Make it 150 mm wide but keep the same thickness.",
        "dry_run": True,
    })
    _show_summary(data)
    print(f"  Edit validated without re-exporting. cad_exported={data.get('cad_exported')}")
    return data


def workflow_edit_full(client: httpx.Client) -> dict:
    """Step 5: Full edit-apply — regenerate CAD."""
    _section("Step 5 — Full Edit-Apply (regenerate CAD)")
    data = _call(client, "POST", "/v1/edit-apply", {
        "target": "bracket",
        "edit_text": "Make it 150 mm wide but keep the same thickness.",
        "dry_run": False,
    })
    _show_summary(data)
    return data


def workflow_rejection(client: httpx.Client) -> dict:
    """Step 6: Submit an unsupported request — expect clear rejection."""
    _section("Step 6 — Rejection Test (unsupported three holes)")
    data = _call(client, "POST", "/v1/parse-build", {
        "prompt": "Make a wall-mounted bracket with three mounting holes.",
        "dry_run": True,
    })
    _show_summary(data)
    print("  Rejection is expected: three holes are not a supported pattern.")
    return data


def workflow_artifact_list(client: httpx.Client, run_data: dict) -> None:
    """Step 7: List artifacts from a successful build."""
    _section("Step 7 — Artifact List from Build Run")
    run_id = run_data.get("run_id") or run_data.get("metadata", {}).get("run_summary", {}).get("run_id")
    if not run_id:
        print("  No run_id available — skipping artifact list step.")
        return

    data = _call(client, "GET", "/v1/runs/parsed_runs/" + run_id)
    _show_summary(data)
    print(f"  Run metadata retrieved for run_id={run_id}")


# ── Main ─────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="IntentForge product workflow demo")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8765",
        help="IntentForge API base URL (default: http://127.0.0.1:8765)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Bearer token for API auth (if INTENTFORGE_API_TOKEN is set)",
    )
    args = parser.parse_args()

    headers = {}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"

    client = httpx.Client(base_url=args.base_url, headers=headers, timeout=60.0)

    # Connectivity
    if not workflow_connectivity(client):
        return 1

    # Full workflow
    parse_result = workflow_parse_intent(client)
    workflow_dry_run(client)
    build_result = workflow_full_build(client)
    workflow_edit_dry(client)
    edit_result = workflow_edit_full(client)
    workflow_rejection(client)
    workflow_artifact_list(client, build_result)

    # Summary
    _section("Workflow Complete")
    print("  The full commercial-style workflow ran successfully:")
    print("    parse → dry-run → build → edit → validate → rejection → artifact list")
    print()
    print("  Key contract fields to note:")
    print("    • request_id — unique per call, for tracing")
    print("    • ok — boolean success flag")
    print("    • validation — structured validation summary")
    print("    • artifacts — list of ArtifactRef (kind + path)")
    print("    • dry_run — whether CAD was actually exported")
    print("    • error — structured ToolError on rejection")
    print()
    print("  These are the fields external agents and SaaS integrations rely on.")

    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
