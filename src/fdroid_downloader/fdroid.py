from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import re
from typing import Iterable

import requests


@dataclass(frozen=True)
class PackageInfo:
    package_name: str
    download_url: str


@dataclass(frozen=True)
class SearchResults:
    query: str
    packages: tuple[str, ...]


class FdroidClient:
    def __init__(
        self,
        *,
        base_url: str = "https://f-droid.org",
        session: requests.Session | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._session = session or requests.Session()

    def get_latest_apk_info(self, package: str, *, search: bool = False) -> PackageInfo:
        package_name = self._resolve_package(package, search=search)
        html = self._fetch_package_page(package_name)
        download_url = self._extract_download_url(html, package_name)
        return PackageInfo(package_name=package_name, download_url=download_url)

    def search_packages(self, query: str) -> SearchResults:
        response = self._session.get(
            f"{self._base_url}/en/packages/",
            params={"q": query},
            timeout=30,
        )
        response.raise_for_status()
        packages = sorted(set(self._extract_package_ids(response.text)))
        return SearchResults(query=query, packages=tuple(packages))

    def download_apk(
        self,
        package: str,
        *,
        dest_dir: str,
        search: bool = False,
    ) -> str:
        info = self.get_latest_apk_info(package, search=search)
        filename = info.download_url.rsplit("/", maxsplit=1)[-1]
        destination = f"{dest_dir.rstrip('/')}/{filename}"
        with self._session.get(info.download_url, stream=True, timeout=60) as response:
            response.raise_for_status()
            with open(destination, "wb") as file_handle:
                for chunk in response.iter_content(chunk_size=1024 * 128):
                    if chunk:
                        file_handle.write(chunk)
        return destination

    def _resolve_package(self, package: str, *, search: bool) -> str:
        if not search:
            return package
        results = self.search_packages(package)
        if not results.packages:
            raise ValueError(f"No packages found for query '{package}'.")
        if package in results.packages:
            return package
        if len(results.packages) == 1:
            return results.packages[0]
        sample = ", ".join(results.packages[:5])
        raise ValueError(
            "Multiple packages matched query "
            f"'{package}': {sample}. Please use an exact package name."
        )

    def _fetch_package_page(self, package_name: str) -> str:
        response = self._session.get(
            f"{self._base_url}/en/packages/{package_name}/",
            timeout=30,
        )
        response.raise_for_status()
        return response.text

    def _extract_download_url(self, html: str, package_name: str) -> str:
        candidates = [
            unescape(match)
            for match in re.findall(r'href="([^"]+?\.apk)"', html)
            if f"/repo/{package_name}_" in match
        ]
        if not candidates:
            raise ValueError(f"Unable to locate APK download for '{package_name}'.")
        url = candidates[0]
        if url.startswith("/"):
            return f"{self._base_url}{url}"
        return url

    def _extract_package_ids(self, html: str) -> Iterable[str]:
        for match in re.findall(r'/en/packages/([^/]+)/', html):
            yield match
