"""EXECUTOR_PACKAGES: one config list feeds both the code runner check and the generator prompt."""

from __future__ import annotations

import pytest

from app.config import Settings, get_settings
from app.generation.principles import common_system, runtime_libraries
from app.subjects import PYTHON_PROFILE
from graders import get_executor
from graders.python import run_python


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_default_packages() -> None:
    assert _settings().executor_packages == ["numpy", "pandas", "matplotlib"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("numpy, scipy", ["numpy", "scipy"]), ("", [])],
)
def test_packages_parse_from_env(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: list[str]
) -> None:
    monkeypatch.setenv("EXECUTOR_PACKAGES", raw)
    assert _settings().executor_packages == expected


def test_generator_prompt_names_configured_packages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXECUTOR_PACKAGES", "numpy,pandas,matplotlib")
    get_settings.cache_clear()
    try:
        assert "standard library and numpy, pandas, matplotlib" in common_system(PYTHON_PROFILE)
        monkeypatch.setenv("EXECUTOR_PACKAGES", "")
        get_settings.cache_clear()
        assert runtime_libraries() == "Code may import only the Python standard library."
    finally:
        get_settings.cache_clear()


def test_default_packages_import_in_the_runner() -> None:
    source = (
        "import numpy as np\nimport pandas as pd\nimport matplotlib.pyplot as plt\n"
        "df = pd.DataFrame({'t': ['A', 'B', 'A'], 'p': np.array([3, 5, 4])})\n"
        "df.groupby('t')['p'].sum().plot(kind='bar')\n"
        "print(df.groupby('t')['p'].sum().to_dict())"
    )
    result = run_python(get_executor(), source, "", 30)
    assert result.exit_code == 0, result.stderr
    assert result.stdout.strip() == "{'A': 7, 'B': 5}"
