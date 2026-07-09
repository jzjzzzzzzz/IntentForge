#!/usr/bin/env python3
"""API client demo for IntentForge HTTP API.

Demonstrates how an external user or agent would call IntentForge
endpoints end-to-end:

  1. Health check
  2. Parse-build with dry_run=True  (validate intent, no CAD export)
  3. Parse-build with dry_run=False (full CAD generation)
  4. Edit-apply with dry_run=True   (validate edit, no export)
  5. Edit-apply with dry_run=False  (full edit + regenerated CAD)

Requires: httpx  (pip install httpx)

Usage:
  # Start the server first:
  python -m intentforge.api.server

  # Then run this demo:
  python examples/api_client_demo.py [--base-url URL] [--token TOKEN]
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


def _banner(label: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")


def _print_response(resp: httpx.Response) -> None:
    """Print the key fields from a ToolResponse envelope."""
    data = resp.json()

    status = resp.status_code
    ok = data.get("ok", "N/A")
    request_id = data.get("request_id", "N/A")
    operation = data.get("operation", "N/A")
    object_type = data.get("object_type", "N/A")
    dry_run = data.get("dry_run", False)

    print(f"  HTTP status   : {status}")
    print(f"  ok            : {ok}")
    print(f"  request_id    : {request_id}")
    print(f"  operation     : {operation}")
    print(f"  object_type   : {object_type}")
    print(f"  dry_run       : {dry_run}")

    # Validation summary
    validation = data.get("validation")
    if validation:
        print(f"  validation    : valid={validation.get('valid')}, "
              f"checks={validation.get('total_checks')}, "
              f"passed={validation.get('passed_checks')}, "
              f"failed={validation.get('failed_checks')}")

    # Artifacts
    artifacts = data.get("artifacts", [])
    if artifacts:
        print(f"  artifacts     : {len(artifacts)}")
        for ref in artifacts:
            print(f"    - {ref.get('kind')} → {ref.get('path')}")

    # Error
    error = data.get("error")
    if error:
        print(f"  error_type    : {error.get('error_type')}")
        print(f"  message       : {error.get('message')}")
        print(f"  recoverable   : {error.get('recoverable')}")

    # Compact extras
    if data.get("cad_exported") is not None:
        print(f"  cad_exported  : {data.get('cad_exported')}")


# ── Demo steps ───────────────────────────────────────────────────────


def step_health(client: httpx.Client) -> None:
    _banner("Step 1: Health Check (GET /health)")
    resp = client.get("/health")
    print(f"  Response: {resp.json()}")
    assert resp.status_code == 200, f"Health check failed: {resp.status_code}"
    print("  ✅ API server is healthy.")


def step_parse_build_dry(client: httpx.Client) -> None:
    _banner("Step 2: Parse-Build (dry_run=True) — validate intent, no CAD export")
    payload = {
        "prompt": "Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with two screw holes.",
        "dry_run": True,
    }
    resp = client.post("/v1/parse-build", json=payload)
    _print_response(resp)
    data = resp.json()
    assert data.get("ok") is True, f"dry_run parse-build should succeed: {data}"
    assert data.get("dry_run") is True, "dry_run flag should be True"
    assert data.get("cad_exported") is False or data.get("cad_exported") is None, \
        "dry_run should not export CAD"
    print("  ✅ Dry-run parse-build validated intent without exporting STEP/STL.")


def step_parse_build_full(client: httpx.Client) -> None:
    _banner("Step 3: Parse-Build (dry_run=False) — full CAD generation + export")
    payload = {
        "prompt": "Make a wall-mounted bracket 100 mm wide, 50 mm tall, 5 mm thick, with four mounting holes.",
        "dry_run": False,
    }
    resp = client.post("/v1/parse-build", json=payload)
    _print_response(resp)
    data = resp.json()
    assert data.get("ok") is True, f"parse-build should succeed: {data}"
    assert data.get("dry_run") is False, "dry_run flag should be False"
    print("  ✅ Full parse-build generated STEP/STL and validation artifacts.")


def step_edit_apply_dry(client: httpx.Client) -> None:
    _banner("Step 4: Edit-Apply (dry_run=True) — validate edit, no re-export")
    payload = {
        "target": "bracket",
        "edit_text": "Make it 150 mm wide but keep the same thickness.",
        "dry_run": True,
    }
    resp = client.post("/v1/edit-apply", json=payload)
    _print_response(resp)
    data = resp.json()
    assert data.get("ok") is True, f"dry_run edit-apply should succeed: {data}"
    assert data.get("dry_run") is True, "dry_run flag should be True"
    print("  ✅ Dry-run edit-apply validated the edit without re-exporting CAD.")


def step_edit_apply_full(client: httpx.Client) -> None:
    _banner("Step 5: Edit-Apply (dry_run=False) — edit + regenerate CAD")
    payload = {
        "target": "bracket",
        "edit_text": "Add a center cutout.",
        "dry_run": False,
    }
    resp = client.post("/v1/edit-apply", json=payload)
    _print_response(resp)
    data = resp.json()
    assert data.get("ok") is True, f"edit-apply should succeed: {data}"
    print("  ✅ Full edit-apply regenerated CAD with the center cutout.")


# ── Main ─────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="IntentForge API client demo")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="IntentForge API base URL (default: http://127.0.0.1:8000)",
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

    # Step 0: connectivity check
    print(f"Connecting to IntentForge API at {args.base_url} ...")
    try:
        probe = client.get("/health")
    except httpx.ConnectError:
        print(
            f"\n❌ Cannot connect to {args.base_url}.\n"
            f"Start the server first:\n"
            f"  python -m intentforge.api.server\n"
            f"  # or:  intentforge serve",
            file=sys.stderr,
        )
        return 1

    # Run demo steps
    step_health(client)
    step_parse_build_dry(client)
    step_parse_build_full(client)
    step_edit_apply_dry(client)
    step_edit_apply_full(client)

    _banner("Demo Complete")
    print("  All 5 steps passed successfully.")
    print("  Review the printed request_id, operation, validation, and artifact refs.")
    print("  Those are the contract-compatible fields that external agents rely on.")

    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
