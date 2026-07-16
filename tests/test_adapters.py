from pathlib import Path

import pytest

from dreamcycle.adapters import AdapterManager
from dreamcycle.errors import ConfigurationError, PromotionError


def make_adapter(path: Path, value: str) -> Path:
    path.mkdir(parents=True)
    (path / "adapter_config.json").write_text(value)
    return path


def test_promote_and_rollback_use_atomic_pointers(tmp_path):
    candidates = tmp_path / "candidates"
    manager = AdapterManager(candidate_root=candidates, active_root=tmp_path / "active")
    first = make_adapter(candidates / "first", "first")
    second = make_adapter(candidates / "second", "second")

    first_result = manager.promote(first, session_id="cycle-one")
    second_result = manager.promote(second, session_id="cycle-two")

    assert first_result.accepted
    assert second_result.previous_path == first_result.promoted_path
    assert manager.active_adapter() == second_result.promoted_path
    assert (second_result.promoted_path / "dreamcycle-promotion.json").is_file()

    rollback = manager.rollback()
    assert rollback.accepted
    assert manager.active_adapter() == first_result.promoted_path


def test_promote_rejects_path_outside_candidate_root(tmp_path):
    candidates = tmp_path / "candidates"
    manager = AdapterManager(candidate_root=candidates, active_root=tmp_path / "active")
    outside = make_adapter(tmp_path / "outside", "outside")

    with pytest.raises(ConfigurationError, match="inside"):
        manager.promote(outside, session_id="cycle")


def test_live_promotion_lock_is_not_ignored(tmp_path):
    candidates = tmp_path / "candidates"
    active = tmp_path / "active"
    manager = AdapterManager(candidate_root=candidates, active_root=active)
    adapter = make_adapter(candidates / "adapter", "value")
    active.mkdir(parents=True)
    (active / ".promotion.lock").write_text("held")

    with pytest.raises(PromotionError, match="in progress"):
        manager.promote(adapter, session_id="cycle")
