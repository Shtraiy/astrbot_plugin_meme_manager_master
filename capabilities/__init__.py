"""Optional capabilities loaded outside the core startup path."""

from .semantic import CapabilityStatus, LazySemanticCapability, Unavailable

__all__ = ["CapabilityStatus", "LazySemanticCapability", "Unavailable"]
