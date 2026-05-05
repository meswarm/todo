"""R2 media store abstraction and local download layout."""
from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlparse

from src.config import R2Config

logger = logging.getLogger(__name__)


def category_for_mime(mime: str) -> str:
    normalized = mime.lower()
    if normalized.startswith("image/"):
        return "imgs"
    if normalized.startswith("video/"):
        return "videos"
    if normalized.startswith("audio/"):
        return "audios"
    return "files"


def local_download_path(downloads_dir: Path, mime: str, filename: str) -> Path:
    return downloads_dir / category_for_mime(mime) / filename


class R2MediaStore:
    """Minimal R2 media store wrapper.

    Non-text media should flow through this layer. Matrix is transport only.
    """

    def __init__(self, config: R2Config, downloads_dir: Path) -> None:
        self._config = config
        self._downloads_dir = downloads_dir

    @property
    def enabled(self) -> bool:
        return bool(
            self._config.endpoint and self._config.access_key and self._config.secret_key
        )

    async def upload(self, local_path: Path, room_prefix: str, mime: str) -> str:
        if not self._config.bucket:
            raise RuntimeError("R2 bucket is not configured")
        key = f"{room_prefix.strip('/')}/{category_for_mime(mime)}/{local_path.name}"
        return f"r2://{self._config.bucket}/{key}"

    async def download(self, r2_uri: str) -> Path | None:
        return await self.download_r2_uri(r2_uri, "file")

    async def download_r2_uri(self, uri: str, media_kind: str) -> Path | None:
        parsed = self._parse_r2_uri(uri)
        if not parsed:
            logger.warning("Invalid R2 URI: %s", uri)
            return None
        if not self.enabled:
            logger.warning("R2 download skipped because credentials or endpoint are missing")
            return None

        bucket, key = parsed
        filename = Path(key).name
        if not filename:
            return None

        target = self._next_available_path(
            local_download_path(
                self._downloads_dir,
                self._media_kind_to_mime(media_kind),
                filename,
            )
        )
        target.parent.mkdir(parents=True, exist_ok=True)

        try:
            payload = self._download_bytes(bucket, key)
        except Exception as exc:
            logger.warning("R2 download failed for %s: %s", uri, exc)
            return None

        try:
            target.write_bytes(payload)
        except OSError as exc:
            logger.warning("Failed to write downloaded R2 object %s: %s", target, exc)
            return None
        return target

    def _download_bytes(self, bucket: str, key: str) -> bytes:
        try:
            import boto3
            from botocore.client import Config as BotoConfig
        except ImportError as exc:
            raise RuntimeError("boto3 is required for R2 downloads") from exc
        client = boto3.client(
            "s3",
            endpoint_url=self._config.endpoint,
            aws_access_key_id=self._config.access_key,
            aws_secret_access_key=self._config.secret_key,
            config=BotoConfig(signature_version="s3v4"),
        )
        response = client.get_object(Bucket=bucket, Key=key)
        body = response["Body"]
        try:
            return body.read()
        finally:
            close = getattr(body, "close", None)
            if callable(close):
                close()

    @staticmethod
    def _parse_r2_uri(uri: str) -> tuple[str, str] | None:
        parsed = urlparse(uri)
        if parsed.scheme != "r2":
            return None
        bucket = parsed.netloc.strip()
        key = parsed.path.lstrip("/")
        if not bucket or not key:
            return None
        return bucket, key

    @staticmethod
    def _media_kind_to_mime(media_kind: str) -> str:
        normalized = media_kind.lower()
        if normalized == "image":
            return "image/png"
        if normalized == "video":
            return "video/mp4"
        if normalized == "audio":
            return "audio/mpeg"
        return "application/octet-stream"

    @staticmethod
    def _next_available_path(path: Path) -> Path:
        if not path.exists():
            return path

        suffixes = "".join(path.suffixes)
        stem = path.name[: -len(suffixes)] if suffixes else path.name
        counter = 1
        candidate = path
        while candidate.exists():
            candidate = path.with_name(f"{stem}_{counter}{suffixes}")
            counter += 1
        return candidate

    async def download_content(self, mime: str, filename: str, content: bytes) -> Path:
        path = local_download_path(self._downloads_dir, mime, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path
