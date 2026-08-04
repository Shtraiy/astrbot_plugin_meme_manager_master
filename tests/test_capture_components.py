import base64
import unittest

from capture_components.vision_gateway import (
    decode_base64_image,
    decode_data_url_image,
    payload_from_content,
)


class CaptureVisionGatewayTests(unittest.TestCase):
    def test_payload_rejects_empty_invalid_and_oversized_content(self):
        detector = lambda content: ".png" if content.startswith(b"PNG") else None
        self.assertIsNone(payload_from_content(b"", 10, detector))
        self.assertIsNone(payload_from_content(b"JPG", 2, detector))
        self.assertIsNone(payload_from_content(b"JPG", 10, detector))

    def test_base64_decode_is_bounded_and_validated(self):
        detector = lambda content: ".png" if content.startswith(b"PNG") else None
        encoded = base64.b64encode(b"PNG-data").decode()
        result = decode_base64_image(encoded, 20, detector)
        self.assertEqual(result.extension, ".png")
        self.assertIsNone(decode_base64_image("not-base64", 20, detector))
        self.assertIsNone(decode_base64_image(encoded, 2, detector))

    def test_data_url_uses_same_validation(self):
        detector = lambda content: ".png" if content.startswith(b"PNG") else None
        encoded = base64.b64encode(b"PNG-data").decode()
        result = decode_data_url_image(f"data:image/png;base64,{encoded}", 20, detector)
        self.assertEqual(result.content, b"PNG-data")
        self.assertIsNone(decode_data_url_image("data:text/plain;base64,QQ==", 20, detector))


if __name__ == "__main__":
    unittest.main()
