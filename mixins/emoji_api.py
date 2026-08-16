from __future__ import annotations

import base64
import io
import mimetypes
from pathlib import Path

from PIL import Image as PILImage
from quart import jsonify, request

from astrbot.api import logger

from ..storage import (
    IMAGE_EXTENSIONS,
    image_preview_mode,
    is_safe_category_segment,
)

MAX_PREVIEW_IMAGE_BYTES = 8 * 1024 * 1024
MAX_ORIGINAL_IMAGE_BYTES = 32 * 1024 * 1024
PREVIEW_IMAGE_MAX_DIMENSION = 512


class EmojiAPIMixin:
    @staticmethod
    def _build_file_data_url(file_path: Path, mime_type: str) -> str:
        with file_path.open("rb") as image_file:
            encoded = base64.b64encode(image_file.read()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    @staticmethod
    def _build_preview_data_url(file_path: Path) -> tuple[str, str]:
        resample_filter = getattr(
            getattr(PILImage, "Resampling", PILImage),
            "LANCZOS",
            PILImage.BICUBIC,
        )
        with PILImage.open(file_path) as image:
            image.thumbnail(
                (PREVIEW_IMAGE_MAX_DIMENSION, PREVIEW_IMAGE_MAX_DIMENSION),
                resample_filter,
            )
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA")
            output = io.BytesIO()
            image.save(output, format="WEBP", quality=82, method=4)
        encoded = base64.b64encode(output.getvalue()).decode("ascii")
        return f"data:image/webp;base64,{encoded}", "image/webp"

    @staticmethod
    def _safe_image_filename(value: str) -> bool:
        normalized = str(value or "").strip()
        return bool(
            normalized
            and normalized not in {".", ".."}
            and Path(normalized).name == normalized
            and "/" not in normalized
            and "\\" not in normalized
            and Path(normalized).suffix.lower() in IMAGE_EXTENSIONS
        )

    async def _api_get_meme_image_data(self):
        category = str(request.args.get("category", "") or "").strip()
        filename = str(request.args.get("filename", "") or "").strip()
        size = request.args.get("size", "preview")
        if not is_safe_category_segment(category) or not self._safe_image_filename(filename):
            return jsonify({"status": "error", "message": "分类或文件名无效"}), 400
        try:
            view_context = self._resolve_webui_pack_view_context()
        except (FileNotFoundError, ValueError) as exc:
            return self._pack_context_error_response(exc)
        memes_root = (
            view_context["memes_dir"].resolve()
            if view_context
            else Path(self._default_pack_context()["memes_dir"]).resolve()
        )
        file_path = (memes_root / filename).resolve()
        if not file_path.is_file():
            legacy_path = (memes_root / category / filename).resolve()
            if legacy_path.is_file():
                file_path = legacy_path

        try:
            file_path.relative_to(memes_root)
        except ValueError:
            return jsonify({"status": "error", "message": "Invalid path"}), 403

        if not file_path.exists() or not file_path.is_file():
            return jsonify({"status": "error", "message": "File not found"}), 404

        file_size = file_path.stat().st_size
        mime_type = (
            mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        )
        preview_mode = image_preview_mode(
            file_size=file_size,
            mime_type=mime_type,
            requested_size=size,
            raw_preview_limit=MAX_PREVIEW_IMAGE_BYTES,
            source_limit=MAX_ORIGINAL_IMAGE_BYTES,
        )
        if preview_mode == "reject":
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Image is too large to preview in the plugin page",
                        "size": file_size,
                        "max_size": MAX_ORIGINAL_IMAGE_BYTES,
                    }
                ),
                413,
            )

        if preview_mode == "thumbnail":
            try:
                data_url, mime_type = self._build_preview_data_url(file_path)
            except Exception as exc:
                if file_size > MAX_PREVIEW_IMAGE_BYTES:
                    logger.warning(f"生成大图预览缩略图失败: {exc}")
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "message": "无法生成图片预览",
                                "size": file_size,
                            }
                        ),
                        422,
                    )
                logger.warning(f"生成预览缩略图失败，回退原图数据: {exc}")
                data_url = self._build_file_data_url(file_path, mime_type)
        else:
            data_url = self._build_file_data_url(file_path, mime_type)

        return jsonify(
            {
                "category": category,
                "filename": filename,
                "mime_type": mime_type,
                "size": file_size,
                "data_url": data_url,
            }
        )
