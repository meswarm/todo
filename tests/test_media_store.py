"""Media store helpers."""

import asyncio

from src.config import R2Config
from src.media_store import R2MediaStore, category_for_mime, local_download_path


class _FakeBody:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def close(self) -> None:
        return None


class _FakeS3Client:
    def __init__(self, payload: bytes = b"", exc: Exception | None = None) -> None:
        self._payload = payload
        self._exc = exc
        self.calls: list[tuple[str, str]] = []

    def get_object(self, Bucket: str, Key: str) -> dict[str, object]:
        self.calls.append((Bucket, Key))
        if self._exc:
            raise self._exc
        return {"Body": _FakeBody(self._payload)}


def _store(tmp_path, bucket: str = "bucket") -> R2MediaStore:
    config = R2Config(
        endpoint="https://example.r2",
        access_key="ak",
        secret_key="sk",
        bucket=bucket,
        public_url="",
    )
    return R2MediaStore(config, tmp_path / "downloads")


def test_download_r2_uri_invalid_uri_returns_none(tmp_path):
    store = _store(tmp_path)

    assert asyncio.run(store.download_r2_uri("https://example.com/not-r2", "file")) is None


def test_download_r2_uri_returns_none_when_credentials_missing(tmp_path):
    config = R2Config(
        endpoint="",
        access_key="",
        secret_key="",
        bucket="bucket",
        public_url="",
    )
    store = R2MediaStore(config, tmp_path / "downloads")

    assert asyncio.run(store.download_r2_uri("r2://bucket/files/report.pdf", "file")) is None


def test_download_r2_uri_uses_bucket_from_uri(tmp_path, monkeypatch):
    store = _store(tmp_path, bucket="configured-bucket")
    fake_client = _FakeS3Client(payload=b"hello")
    monkeypatch.setattr(store, "_download_bytes", lambda bucket, key: fake_client.get_object(Bucket=bucket, Key=key)["Body"].read())

    target = asyncio.run(store.download_r2_uri("r2://other-bucket/files/report.pdf", "file"))

    assert target == tmp_path / "downloads" / "files" / "report.pdf"
    assert target.read_bytes() == b"hello"
    assert fake_client.calls == [("other-bucket", "files/report.pdf")]


def test_download_r2_uri_returns_none_on_download_failure(tmp_path, monkeypatch):
    store = _store(tmp_path)
    monkeypatch.setattr(store, "_download_bytes", lambda bucket, key: (_ for _ in ()).throw(RuntimeError("boom")))

    result = asyncio.run(store.download_r2_uri("r2://bucket/files/report.pdf", "file"))

    assert result is None
    assert not (tmp_path / "downloads" / "files" / "report.pdf").exists()


def test_download_r2_uri_success_uses_kind_directory_and_unique_name(tmp_path, monkeypatch):
    store = _store(tmp_path)
    existing = tmp_path / "downloads" / "imgs" / "cat.png"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_bytes(b"previous")
    monkeypatch.setattr(store, "_download_bytes", lambda bucket, key: b"new-content")

    target = asyncio.run(store.download_r2_uri("r2://bucket/assets/cats/cat.png", "image"))

    assert target == tmp_path / "downloads" / "imgs" / "cat_1.png"
    assert target.read_bytes() == b"new-content"


def test_category_for_mime():
    assert category_for_mime("image/png") == "imgs"
    assert category_for_mime("video/mp4") == "videos"
    assert category_for_mime("audio/mpeg") == "audios"
    assert category_for_mime("application/pdf") == "files"


def test_local_download_path_uses_category(tmp_path):
    target = local_download_path(tmp_path, "image/png", "demo.png")
    assert target == tmp_path / "imgs" / "demo.png"


def test_upload_uri_format(tmp_path):
    config = R2Config(
        endpoint="https://example.r2",
        access_key="ak",
        secret_key="sk",
        bucket="bkt",
        public_url="",
    )
    store = R2MediaStore(config, tmp_path / "downloads")
    sample = tmp_path / "sample.bin"
    sample.write_bytes(b"hello")
    uri = asyncio.run(store.upload(sample, "room1", "application/octet-stream"))
    assert uri == "r2://bkt/room1/files/sample.bin"
