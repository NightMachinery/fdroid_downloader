from __future__ import annotations

from pathlib import Path

import pytest
import requests

from fdroid_downloader.fdroid import FdroidClient, PackageInfo


class FakeResponse:
    def __init__(self, *, status_code: int, content: bytes = b"") -> None:
        self.status_code = status_code
        self._content = content
        self.headers: dict[str, str] = {}

    def iter_content(self, chunk_size: int = 1024) -> list[bytes]:
        return [self._content] if self._content else []

    def raise_for_status(self) -> None:
        if 400 <= self.status_code:
            raise requests.HTTPError(f"status {self.status_code}")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None


@pytest.mark.parametrize("package_name", ["se.lublin.mumla", "chat.delta.lite"])
def test_get_latest_apk_info(package_name: str) -> None:
    client = FdroidClient()
    info = client.get_latest_apk_info(package_name)
    assert info.download_url.startswith("https://f-droid.org/repo/")
    assert info.download_url.endswith(".apk")
    response = requests.head(info.download_url, timeout=30)
    assert response.status_code == 200


def test_download_apk_uses_partial_and_resumes(tmp_path: Path) -> None:
    client = FdroidClient()
    package_info = PackageInfo(
        package_name="com.example.app",
        download_url="https://example.com/repo/app.apk",
    )
    client.get_latest_apk_info = lambda *args, **kwargs: package_info

    calls: list[dict[str, str]] = []

    def fake_get(url: str, *, stream: bool, timeout: int, headers: dict[str, str]):
        calls.append(headers)
        if headers.get("Range"):
            return FakeResponse(status_code=206, content=b"world")
        return FakeResponse(status_code=200, content=b"hello ")

    client._session.get = fake_get  # type: ignore[assignment]

    partial_path = tmp_path / "app.apk.partial"
    partial_path.write_bytes(b"hello ")

    result = client.download_apk("com.example.app", dest_dir=str(tmp_path))

    assert calls[0]["Range"] == "bytes=6-"
    assert result == str(tmp_path / "app.apk")
    assert (tmp_path / "app.apk").read_bytes() == b"hello world"
    assert not partial_path.exists()


def test_download_apk_prefers_aria2c(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = FdroidClient()
    package_info = PackageInfo(
        package_name="com.example.app",
        download_url="https://example.com/repo/app.apk",
    )
    client.get_latest_apk_info = lambda *args, **kwargs: package_info

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/aria2c")

    captured: dict[str, list[str]] = {}

    def fake_run(command, *, check, capture_output, text):
        captured["command"] = command
        destination = tmp_path / "app.apk.partial"
        destination.write_bytes(b"payload")

        class Result:
            returncode = 0
            stderr = ""

        return Result()

    monkeypatch.setattr("subprocess.run", fake_run)

    result = client.download_apk("com.example.app", dest_dir=str(tmp_path))

    assert captured["command"][0] == "aria2c"
    assert result == str(tmp_path / "app.apk")
    assert (tmp_path / "app.apk").read_bytes() == b"payload"
