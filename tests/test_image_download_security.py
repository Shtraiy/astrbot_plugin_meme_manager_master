import asyncio
import io
import unittest
from unittest.mock import patch
from pathlib import Path

from PIL import Image

from tests.fakes import install_package_alias, install_runtime_stubs


install_runtime_stubs()
install_package_alias()

from meme_manager_master.backend.image_download import (  # noqa: E402
    ImageDownload,
    is_safe_image_url,
    validate_image_payload,
)


class ImageDownloadSecurityTests(unittest.TestCase):
    def test_message_upload_path_uses_shared_safe_downloader(self):
        source = (Path(__file__).resolve().parents[1] / "mixins" / "event_handlers.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("download_image", source)
        self.assertNotIn("CERT_NONE", source)
        self.assertNotIn('replace("https://", "http://", 1)', source)

    def test_rejects_non_https_and_local_image_urls(self):
        self.assertFalse(is_safe_image_url("http://example.com/image.png"))
        self.assertFalse(is_safe_image_url("https://127.0.0.1/image.png"))
        self.assertFalse(is_safe_image_url("https://localhost/image.png"))
        self.assertFalse(is_safe_image_url("https://user:pass@example.com/image.png"))

    def test_validates_real_image_format_and_limit(self):
        output = io.BytesIO()
        Image.new("RGB", (2, 2), "red").save(output, format="PNG")
        content = output.getvalue()

        result = validate_image_payload(content, len(content))

        self.assertEqual(result, ImageDownload(content, ".png"))
        self.assertIsNone(validate_image_payload(b"not an image", 1024))
        self.assertIsNone(validate_image_payload(content, len(content) - 1))

    def test_download_rejects_redirects_and_oversized_payloads(self):
        from meme_manager_master.backend import image_download

        class Response:
            status = 302
            headers = {"Content-Length": "100"}

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

        class Session:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

            def get(self, url, **kwargs):
                self.url = url
                self.request_kwargs = kwargs
                return Response()

        async def run():
            with patch.object(image_download, "_remote_target_is_public", return_value=True):
                with patch.object(image_download.aiohttp, "ClientSession", Session):
                    return await image_download.download_image(
                        "https://example.com/image.png", 1024, timeout_seconds=5
                    )

        self.assertIsNone(asyncio.run(run()))


if __name__ == "__main__":
    unittest.main()
