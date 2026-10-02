"""Registry behaviour beyond the frozen contract test (C5 review fixes)."""

from __future__ import annotations

import builtins

import pytest

from graders import registry


@pytest.fixture(autouse=True)
def _fresh_registry():
    registry.set_executor(None)
    yield
    registry.set_executor(None)


def test_a_missing_dependency_drops_only_its_own_capabilities(monkeypatch) -> None:
    import sys

    real_import = builtins.__import__
    monkeypatch.delitem(sys.modules, "graders.quantity", raising=False)

    def no_pint(name, *args, **kwargs):
        if name == "pint" or name.startswith("pint."):
            raise ModuleNotFoundError("No module named 'pint'", name="pint")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_pint)
    available = registry.available_capabilities()
    assert "quantity.units" not in available
    assert "structured.choice" in available
    assert "code.python.tests" in available
