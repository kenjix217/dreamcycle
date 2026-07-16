"""Verify release artifacts contain the expected license and package metadata."""

from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path


def verify(path: Path) -> None:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            metadata = _read_named(archive, names, "METADATA")
    elif path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as archive:
            names = archive.getnames()
            metadata = _read_named(archive, names, "PKG-INFO")
    else:
        raise ValueError(f"unsupported distribution artifact: {path}")

    basenames = {Path(name).name for name in names}
    missing = {"LICENSE", "NOTICE"} - basenames
    if missing:
        raise AssertionError(f"{path} is missing: {', '.join(sorted(missing))}")
    if b"License-Expression: Apache-2.0" not in metadata:
        raise AssertionError(f"{path} does not declare Apache-2.0")


def _read_named(archive: object, names: list[str], basename: str) -> bytes:
    matches = [name for name in names if Path(name).name == basename]
    if len(matches) != 1:
        raise AssertionError(f"expected one {basename}, found {len(matches)}")
    if isinstance(archive, zipfile.ZipFile):
        return archive.read(matches[0])
    member = archive.extractfile(matches[0])
    if member is None:
        raise AssertionError(f"could not read {matches[0]}")
    return member.read()


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: verify_distribution.py DIST [DIST ...]")
    for value in sys.argv[1:]:
        verify(Path(value))


if __name__ == "__main__":
    main()
