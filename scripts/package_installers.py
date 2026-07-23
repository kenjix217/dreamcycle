#!/usr/bin/env python3
"""Build GitHub Release install bundles for Linux and macOS."""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLATFORMS = ("linux-x86_64", "linux-arm64", "macos-x86_64", "macos-arm64")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build DreamCycle install bundles")
    parser.add_argument("--version", default=_project_version())
    parser.add_argument("--dist-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--dashboard-dist", type=Path, default=ROOT / "dashboard" / "dist")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "release")
    args = parser.parse_args()

    version = args.version.removeprefix("v")
    wheel = _wheel(args.dist_dir, version)
    dashboard_dist = args.dashboard_dist.resolve()
    if not (dashboard_dist / "index.html").is_file():
        raise SystemExit(f"dashboard build is missing: {dashboard_dist}")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    checksums: list[str] = []

    for platform in PLATFORMS:
        archive = output_dir / f"dreamcycle-{version}-{platform}.tar.gz"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / f"dreamcycle-{version}-{platform}"
            _stage_bundle(root, version, platform, wheel, dashboard_dist)
            with tarfile.open(archive, "w:gz") as tar:
                tar.add(root, arcname=root.name)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        checksums.append(f"{digest}  {archive.name}")
        print(f"built {archive}")

    checksum_path = output_dir / "SHA256SUMS"
    checksum_path.write_text("\n".join(checksums) + "\n", encoding="utf-8")
    print(f"built {checksum_path}")


def _project_version() -> str:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version = "([^"]+)"$', pyproject)
    if match is None:
        raise SystemExit("could not read project version from pyproject.toml")
    return match.group(1)


def _wheel(dist_dir: Path, version: str) -> Path:
    wheel = dist_dir.resolve() / f"dreamcycle-{version}-py3-none-any.whl"
    if not wheel.is_file():
        raise SystemExit(f"wheel is missing: {wheel}")
    return wheel


def _stage_bundle(
    root: Path,
    version: str,
    platform: str,
    wheel: Path,
    dashboard_dist: Path,
) -> None:
    (root / "wheels").mkdir(parents=True)
    (root / "dashboard").mkdir()
    shutil.copy2(ROOT / "scripts" / "install.sh", root / "install.sh")
    shutil.copy2(ROOT / "scripts" / "dashboard_server.py", root / "dashboard" / "server.py")
    shutil.copy2(wheel, root / "wheels" / wheel.name)
    shutil.copytree(dashboard_dist, root / "dashboard" / "dist")
    (root / "VERSION").write_text(version + "\n", encoding="utf-8")
    (root / "PLATFORM").write_text(platform + "\n", encoding="utf-8")
    (root / "README_INSTALL.md").write_text(_readme(version, platform), encoding="utf-8")
    (root / "install.sh").chmod(0o755)
    (root / "dashboard" / "server.py").chmod(0o755)


def _readme(version: str, platform: str) -> str:
    return f"""# DreamCycle {version} installer for {platform}

Run:

```bash
./install.sh
```

This creates a Python virtual environment under `~/.dreamcycle`, installs the
bundled DreamCycle wheel, installs the built dashboard, and writes command
wrappers to `~/.local/bin`.
"""


if __name__ == "__main__":
    main()
