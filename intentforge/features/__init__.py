"""Feature flag helpers for optional bracket features."""

from intentforge.features.flags import (
    ACTIVE_STATES,
    FEATURE_PARAMETER_MAP,
    OPTIONAL_FEATURES,
    SUPPORTED_HOLE_PATTERNS,
    feature_flags_for_parameter_table,
    feature_for_parameter,
    hole_pattern_for_count,
    is_feature_active,
    make_feature_flag,
    make_mounting_hole_flag,
    mounting_hole_count_from_flags,
    mounting_hole_pattern_from_flags,
    normalize_feature_flags,
)

__all__ = [
    "ACTIVE_STATES",
    "FEATURE_PARAMETER_MAP",
    "OPTIONAL_FEATURES",
    "SUPPORTED_HOLE_PATTERNS",
    "feature_flags_for_parameter_table",
    "feature_for_parameter",
    "hole_pattern_for_count",
    "is_feature_active",
    "make_feature_flag",
    "make_mounting_hole_flag",
    "mounting_hole_count_from_flags",
    "mounting_hole_pattern_from_flags",
    "normalize_feature_flags",
]
