"""Deterministic safe-rejection envelopes for unregistered topologies."""

from __future__ import annotations

import hashlib
import json
from typing import Any


SAFE_REJECTION_SCHEMA_VERSION = "1.0"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def build_safe_rejection_envelope(
    *,
    requested_family: str | None,
    message: str,
    input_kind: str,
) -> dict[str, Any]:
    """Return an immutable rejection record with a SHA-256 integrity address.

    The digest proves content integrity and is intentionally not described as
    an identity signature: IntentForge does not manage signing keys.
    """

    payload = {
        "schema_version": SAFE_REJECTION_SCHEMA_VERSION,
        "state": "safe_rejection",
        "requested_family": requested_family or "unresolved",
        "input_kind": input_kind,
        "boundary": "unregistered_topology_family",
        "message": message,
        "cad_exported": False,
        "geometry_success_claimed": False,
        "safe_rejection_handling_passed": True,
    }
    digest = hashlib.sha256(_canonical_bytes(payload)).hexdigest()
    return {
        **payload,
        "integrity": {
            "algorithm": "sha256",
            "content_address": f"sha256:{digest}",
            "authentication": "not_cryptographically_signed",
        },
    }
