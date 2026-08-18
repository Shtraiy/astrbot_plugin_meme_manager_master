import asyncio
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from tests.fakes import install_package_alias, install_runtime_stubs


install_runtime_stubs()
install_package_alias()

from meme_manager_master.capture import CaptureMixin, ImagePayload  # noqa: E402
from meme_manager_master.backend.image_download import ImageDownload  # noqa: E402
from meme_manager_master import capture as capture_module  # noqa: E402


def _capture_instance():
    instance = CaptureMixin.__new__(CaptureMixin)
    instance.runtime_config = types.SimpleNamespace(download_timeout=5)
    return instance


class CaptureDownloadSecurityTests(unittest.TestCase):
    def test_capture_module_uses_shared_safe_downloader(self):
        source = (Path(__file__).parents[1] / "capture.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("download_image", source)
        self.assertNotIn("aiohttp", source)
        self.assertNotIn("_remote_target_is_public", source)
        self.assertNotIn("socket", source)

    def test_capture_download_rejects_private_ip_literal_without_network(self):
        instance = _capture_instance()

        async def run():
            with patch.object(
                capture_module,
                "download_image",
                new=AsyncMock(),
            ) as mocked:
                result = await instance._download_image(
                    "https://127.0.0.1/image.png", 1024
                )
                return result, mocked

        result, mocked = asyncio.run(run())
        self.assertIsNone(result)
        mocked.assert_not_awaited()

    def test_capture_download_http_url_goes_to_https_only_downloader(self):
        instance = _capture_instance()

        async def run():
            with patch.object(
                capture_module,
                "download_image",
                new=AsyncMock(return_value=None),
            ) as mocked:
                result = await instance._download_image(
                    "http://example.com/image.png", 1024
                )
                return result, mocked

        result, mocked = asyncio.run(run())
        self.assertIsNone(result)
        mocked.assert_awaited_once_with(
            "http://example.com/image.png",
            1024,
            timeout_seconds=5,
        )

    def test_capture_download_success_wraps_shared_payload(self):
        instance = _capture_instance()

        async def run():
            with patch.object(
                capture_module,
                "download_image",
                new=AsyncMock(
                    return_value=ImageDownload(b"image-bytes", ".png")
                ),
            ):
                return await instance._download_image(
                    "https://example.com/image.png", 1024
                )

        result = asyncio.run(run())
        self.assertEqual(result, ImagePayload(b"image-bytes", ".png"))

    def test_capture_download_failure_returns_none(self):
        instance = _capture_instance()

        async def run():
            with patch.object(
                capture_module,
                "download_image",
                new=AsyncMock(return_value=None),
            ):
                return await instance._download_image(
                    "https://example.com/image.png", 1024
                )

        self.assertIsNone(asyncio.run(run()))


if __name__ == "__main__":
    unittest.main()
