import builtins

import pytest

from dreamcycle.errors import OptionalDependencyError
from dreamcycle.training.transformers import _training_imports


def test_missing_training_extra_has_actionable_error(monkeypatch):
    original_import = builtins.__import__

    def fail_peft(name, *args, **kwargs):
        if name == "peft":
            raise ImportError("peft is intentionally absent")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_peft)

    with pytest.raises(OptionalDependencyError, match=r"dreamcycle\[training\]"):
        _training_imports()
