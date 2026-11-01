"""Isolated capability graders (docs/GENERIC_ASSESSMENT_MILESTONES.md, track C).

Standalone: imports only the standard library, pydantic, pint and sympy -- never ``app``.
The app asks :func:`get_grader` for a capability and calls ``check_spec`` / ``grade``.
"""

from graders.core import Grader, GradeResult, SpecError, SpecIssue, TestResult, parse_spec
from graders.executors.base import ExecutorError
from graders.registry import available_capabilities, get_executor, get_grader, set_executor

__all__ = [
    "ExecutorError",
    "GradeResult",
    "Grader",
    "SpecError",
    "SpecIssue",
    "TestResult",
    "available_capabilities",
    "get_executor",
    "get_grader",
    "parse_spec",
    "set_executor",
]
