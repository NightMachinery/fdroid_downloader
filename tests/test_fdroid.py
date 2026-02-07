from __future__ import annotations

import pytest
import requests

from fdroid_downloader.fdroid import FdroidClient


@pytest.mark.parametrize("package_name", ["se.lublin.mumla", "chat.delta.lite"])
def test_get_latest_apk_info(package_name: str) -> None:
    client = FdroidClient()
    info = client.get_latest_apk_info(package_name)
    assert info.download_url.startswith("https://f-droid.org/repo/")
    assert info.download_url.endswith(".apk")
    response = requests.head(info.download_url, timeout=30)
    assert response.status_code == 200
