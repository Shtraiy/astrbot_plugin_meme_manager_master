"""Compatibility import for the legacy cleanup adapter."""

try:
    from ..infrastructure.legacy_cleanup import cleanup_legacy_semantic_data
except ImportError:  # standalone test imports from repository root
    from infrastructure.legacy_cleanup import cleanup_legacy_semantic_data

__all__ = ["cleanup_legacy_semantic_data"]
