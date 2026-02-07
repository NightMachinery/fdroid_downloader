from __future__ import annotations

import argparse
from pathlib import Path

from fdroid_downloader.fdroid import FdroidClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download APKs from F-Droid.")
    default_dir = "."
    parser.add_argument(
        "packages",
        nargs="+",
        help="Package names or search queries to download.",
    )
    parser.add_argument(
        "-d",
        "--dir",
        default=default_dir,
        help=f"Output directory (default: {default_dir})",
    )
    parser.add_argument(
        "--search",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable fuzzy searching in F-Droid.",
    )
    return parser


def run(
    packages: list[str],
    *,
    dest_dir: Path,
    search: bool,
    client: FdroidClient | None = None,
) -> list[Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    fdroid_client = client or FdroidClient()
    downloaded: list[Path] = []
    for package in packages:
        path = fdroid_client.download_apk(
            package,
            dest_dir=str(dest_dir),
            search=search,
        )
        downloaded.append(Path(path))
    return downloaded


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    run(
        args.packages,
        dest_dir=Path(args.dir),
        search=args.search,
    )


if __name__ == "__main__":
    main()
