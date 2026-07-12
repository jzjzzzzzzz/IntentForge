"""Compatibility exports for the standalone offline package verifier."""

from intentforge.offline_verify import (
    OFFLINE_VERIFIER_VERSION,
    OfflineVerificationResult,
    verify_offline_audit_package,
)

__all__ = [
    "OFFLINE_VERIFIER_VERSION",
    "OfflineVerificationResult",
    "verify_offline_audit_package",
]
