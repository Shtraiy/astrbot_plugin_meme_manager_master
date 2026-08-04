"""Framework-independent capture helpers.

The legacy :mod:`capture` module remains the compatibility hook.  These helpers
hold deterministic image and receipt operations so the hook can be migrated in
small, reversible steps.
"""

from .vision_gateway import decode_base64_image, decode_data_url_image, payload_from_content

__all__ = ["decode_base64_image", "decode_data_url_image", "payload_from_content"]
