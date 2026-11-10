"""The tool-call eval's scoring and its case file, without any model call."""

from __future__ import annotations

import yaml

from scripts.eval_agent_tools import CASES, Call, check


def test_check_reports_each_kind_of_miss() -> None:
    calls = [
        Call("read_material", {"book_id": 1}),
        Call("set_course_subject", {"subject": "intro_python"}, pending=True),
        Call("show_design", {"design_id": "d"}),
        Call("show_design", {"design_id": "d"}),
    ]
    problems = check(
        calls,
        "See T1.S2 for details",
        {
            "include": ["design_curriculum"],
            "exclude": ["read_material"],
            "order": [["show_design", "read_material"]],
            "max": {"show_design": 1},
            "args": {"set_course_subject": {"subject": {"not": "intro_python"}}},
            "not_pending": ["set_course_subject"],
            "text_excludes": [r"\bT\d+\.S\d+\b"],
        },
    )
    assert problems == [
        "design_curriculum was not called",
        "read_material was called",
        "show_design did not come before read_material",
        "show_design called 2 times (max 1)",
        "set_course_subject.subject = 'intro_python', wanted {'not': 'intro_python'}",
        "set_course_subject asked for approval",
        "reply matches " + repr(r"\bT\d+\.S\d+\b"),
    ]
    assert check(calls, "", {"include": ["read_material"], "pending": ["set_course_subject"]}) == []


def test_every_case_names_only_tools_the_agent_has() -> None:
    import app.agent.agent  # noqa: F401  (registers the tools)
    from app.agent.tools import toolset

    known = set(toolset.tools)
    cases = yaml.safe_load(CASES.read_text(encoding="utf-8"))["cases"]
    assert len({c["id"] for c in cases}) == len(cases)
    for case in cases:
        for expect in (case.get("expect", {}), case.get("expect_all", {})):
            named = set(expect.get("include", [])) | set(expect.get("exclude", []))
            named |= set(expect.get("max", {})) | set(expect.get("args", {}))
            named |= {n for pair in expect.get("order", []) for n in pair}
            named |= set(expect.get("pending", [])) | set(expect.get("not_pending", []))
            assert named <= known, (case["id"], named - known)
        assert set(case.get("approve", [])) <= known
