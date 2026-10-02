"""The graders package must stay isolated from the application (track C, decision 1)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

GRADERS = Path(__file__).resolve().parents[2] / "graders"
#: Everything a grader may import beyond the standard library.
ALLOWED_THIRD_PARTY = {"pydantic", "pint", "sympy", "httpx", "graders"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


@pytest.mark.parametrize("path", sorted(GRADERS.rglob("*.py")), ids=lambda p: p.name)
def test_no_grader_imports_the_app(path: Path) -> None:
    imported = _imports(path)
    assert "app" not in imported, f"{path.name} imports the app"
    import sys

    stdlib = set(sys.stdlib_module_names)
    foreign = {name for name in imported if name not in stdlib and name not in ALLOWED_THIRD_PARTY}
    assert not foreign, f"{path.name} imports {sorted(foreign)}"


def test_the_contract_types_behave() -> None:
    from pydantic import BaseModel

    from graders import GradeResult, SpecError, parse_spec

    with pytest.raises(ValueError):
        GradeResult(score=1.5)

    class Spec(BaseModel):
        expected: str

    with pytest.raises(SpecError) as error:
        parse_spec(Spec, {})
    assert "expected" in str(error.value)
