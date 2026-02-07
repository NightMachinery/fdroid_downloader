from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from pathlib import Path
import re
import shutil
import subprocess
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
        trust_env: bool = True,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._session = session or requests.Session()
        self._session.trust_env = trust_env

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
        destination = Path(dest_dir) / filename
        partial_destination = Path(f"{destination}.partial")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if self._is_aria2c_available():
            self._download_with_aria2c(info.download_url, partial_destination)
        else:
            self._download_with_requests(info.download_url, partial_destination)
        partial_destination.replace(destination)
        return str(destination)

    def _is_aria2c_available(self) -> bool:
        return shutil.which("aria2c") is not None

    def _download_with_aria2c(self, url: str, destination: Path) -> None:
        command = [
            "aria2c",
            "--continue=true",
            "--allow-overwrite=true",
            "--file-allocation=none",
            "--dir",
            str(destination.parent),
            "--out",
            destination.name,
            url,
        ]
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "aria2c failed with exit code "
                f"{result.returncode}: {result.stderr.strip()}"
            )

    def _download_with_requests(self, url: str, destination: Path) -> None:
        resume_from = destination.stat().st_size if destination.exists() else 0
        headers: dict[str, str] = {}
        mode = "wb"
        if resume_from:
            headers["Range"] = f"bytes={resume_from}-"
            mode = "ab"
        with self._session.get(
            url,
            stream=True,
            timeout=60,
            headers=headers,
        ) as response:
            if response.status_code == 416 and resume_from:
                return
            response.raise_for_status()
            if resume_from and response.status_code == 200:
                mode = "wb"
            with open(destination, mode) as file_handle:
                for chunk in response.iter_content(chunk_size=1024 * 128):
                    if chunk:
                        file_handle.write(chunk)

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
