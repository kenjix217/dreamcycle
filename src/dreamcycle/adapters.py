"""Filesystem-backed adapter activation and rollback.

Adapted from the JintellarCore Dream Engine adapter promotion module.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

from dreamcycle.errors import ConfigurationError, PromotionError
from dreamcycle.types import PromotionResult


class AdapterManager:
    def __init__(
        self,
        *,
        candidate_root: Path,
        active_root: Path,
        stale_lock_seconds: float = 1800,
    ) -> None:
        self._candidate_root = candidate_root.resolve()
        self._active_root = active_root.resolve()
        self._versions_root = self._active_root / "versions"
        self._stale_lock_seconds = stale_lock_seconds
        if stale_lock_seconds <= 0:
            raise ConfigurationError("stale_lock_seconds must be positive")

    def promote(
        self,
        adapter_path: Path,
        *,
        session_id: str,
        metrics: Mapping[str, object] | None = None,
    ) -> PromotionResult:
        candidate = self._contained(adapter_path, self._candidate_root, "adapter_path")
        if not candidate.is_dir():
            raise PromotionError(f"adapter directory does not exist: {candidate}")
        self._versions_root.mkdir(parents=True, exist_ok=True)

        with self._promotion_lock():
            previous = self.active_adapter()
            safe_session = "".join(ch for ch in session_id if ch.isalnum() or ch in "-_")
            if not safe_session:
                raise PromotionError("session_id cannot form an adapter version name")
            version_name = f"{safe_session}-{candidate.name}"
            destination = self._versions_root / version_name
            temporary = self._versions_root / f".{version_name}.tmp-{os.getpid()}"
            if destination.exists():
                raise PromotionError(f"adapter version already exists: {destination}")
            shutil.rmtree(temporary, ignore_errors=True)
            try:
                shutil.copytree(candidate, temporary)
                manifest = {
                    "session_id": session_id,
                    "source_path": str(candidate),
                    "metrics": dict(metrics or {}),
                    "promoted_at": time.time(),
                }
                (temporary / "dreamcycle-promotion.json").write_text(
                    json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                os.replace(temporary, destination)
                if previous is not None:
                    self._write_pointer("PREVIOUS", previous)
                self._write_pointer("ACTIVE", destination)
            except OSError as exc:
                shutil.rmtree(temporary, ignore_errors=True)
                raise PromotionError(f"failed to promote adapter: {exc}") from exc

        return PromotionResult(
            accepted=True,
            reason="all quality gates passed",
            promoted_path=destination,
            previous_path=previous,
            metrics=dict(metrics or {}),
        )

    def rollback(self) -> PromotionResult:
        self._versions_root.mkdir(parents=True, exist_ok=True)
        with self._promotion_lock():
            current = self.active_adapter()
            previous = self._read_pointer("PREVIOUS")
            if previous is None:
                return PromotionResult(
                    accepted=False,
                    reason="no previous adapter is available",
                    promoted_path=current,
                )
            self._write_pointer("ACTIVE", previous)
            (self._active_root / "PREVIOUS").unlink(missing_ok=True)
        return PromotionResult(
            accepted=True,
            reason="previous adapter restored",
            promoted_path=previous,
            previous_path=current,
        )

    def active_adapter(self) -> Path | None:
        return self._read_pointer("ACTIVE")

    def _read_pointer(self, name: str) -> Path | None:
        pointer = self._active_root / name
        if not pointer.exists():
            return None
        value = pointer.read_text(encoding="utf-8").strip()
        if not value:
            raise PromotionError(f"{name} adapter pointer is empty")
        candidate = Path(value)
        resolved = self._contained(candidate, self._versions_root, f"{name} pointer")
        if not resolved.is_dir():
            raise PromotionError(f"{name} adapter directory does not exist: {resolved}")
        return resolved

    def _write_pointer(self, name: str, value: Path) -> None:
        resolved = self._contained(value, self._versions_root, f"{name} pointer")
        self._active_root.mkdir(parents=True, exist_ok=True)
        temporary = self._active_root / f".{name}.tmp-{os.getpid()}"
        temporary.write_text(str(resolved) + "\n", encoding="utf-8")
        os.replace(temporary, self._active_root / name)

    @contextmanager
    def _promotion_lock(self) -> Iterator[None]:
        self._active_root.mkdir(parents=True, exist_ok=True)
        lock_path = self._active_root / ".promotion.lock"
        while True:
            try:
                descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.write(descriptor, f"{os.getpid()} {time.time()}\n".encode())
                os.close(descriptor)
                break
            except FileExistsError as exc:
                try:
                    age = time.time() - lock_path.stat().st_mtime
                except FileNotFoundError:
                    continue
                if age <= self._stale_lock_seconds:
                    raise PromotionError("another adapter promotion is in progress") from exc
                lock_path.unlink(missing_ok=True)
        try:
            yield
        finally:
            lock_path.unlink(missing_ok=True)

    @staticmethod
    def _contained(path: Path, root: Path, label: str) -> Path:
        resolved = path.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ConfigurationError(f"{label} must be inside {root}") from exc
        return resolved
