from app.config import MediaStoreConfig
from app.media_upload import MediaUploader, PresignResponse


def make_config(upload_host_override: str = "") -> MediaStoreConfig:
    return MediaStoreConfig(
        base_url="http://localhost:5106",
        presign_endpoint="/api/v1/media/images/presign",
        complete_endpoint="/api/v1/media/images/complete",
        timeout_seconds=3,
        max_retries=1,
        upload_host_override=upload_host_override,
    )


def test_media_uploader_ignores_environment_proxies():
    uploader = MediaUploader(make_config())
    assert uploader.session.trust_env is False


def test_upload_image_rewrites_host_when_override_is_configured(monkeypatch):
    uploader = MediaUploader(make_config("localhost:9000"))
    captured = {}

    class DummyResponse:
        status_code = 200
        text = "ok"

    def fake_put(url, data, headers, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr(uploader.session, "put", fake_put)

    presign = PresignResponse(
        upload_url="http://minio:9000/farmiq-media/test-object?X-Amz-Signature=abc",
        object_key="farmiq-media/test-object",
        expires_in=300,
        required_headers={"x-amz-acl": "private"},
    )

    ok = uploader.upload_image(b"binary", presign, "image/jpeg")

    assert ok is True
    assert captured["url"].startswith("http://localhost:9000/farmiq-media/test-object")
    assert captured["headers"]["Host"] == "minio:9000"
    assert captured["headers"]["x-amz-acl"] == "private"
    assert captured["headers"]["Content-Type"] == "image/jpeg"
