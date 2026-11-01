"""C5 acceptance: grading through ``graders/`` changes no score.

Every case is scored twice -- by the frozen pre-move scorer (``tests/grading_oracle.py``) and by
the current ``app.adaptive.scoring.score_answer`` -- and the two must agree on score, test counts
and feedback. The real-data replay over every stored attempt is ``scripts/replay_grading.py``.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import grading_oracle

from app.adaptive.scoring import score_answer
from app.domain.enums import Difficulty, QuestionKind, QuestionType
from app.domain.questions import Question
from app.errors import DomainRuleError


def _q(question_type: QuestionType, content: dict, tests: str | None = None) -> Question:
    kind = (
        QuestionKind.TESTABLE_PROGRAM
        if question_type
        in (QuestionType.CODE_COMPLETION, QuestionType.DEBUGGING, QuestionType.CODING)
        else QuestionKind.DISCRETE
    )
    return Question(
        id=7,
        prompt="A question.",
        question_type=question_type,
        kind=kind,
        difficulty=Difficulty.EASY,
        content=content,
        tests=tests,
    )


MCQ = _q(
    QuestionType.MULTIPLE_CHOICE,
    {"options": ["(1,2)", "[1,2]", "{1:2}"], "correct_option_index": 1, "explanation": "Lists."},
)
MCQ_BLANK_EXPLANATION = _q(
    QuestionType.MULTIPLE_CHOICE,
    {"options": ["a", "b"], "correct_option_index": 0, "explanation": "  "},
)
TF = _q(QuestionType.TRUE_FALSE, {"correct_answer": False, "explanation": "No."})
OUTPUT = _q(
    QuestionType.OUTPUT_PREDICTION,
    {"code": "print(1)", "expected_output": "1\n", "explanation": "x"},
)
PARSONS = _q(
    QuestionType.PARSONS,
    {
        "blocks": [
            {"id": "1", "text": "for i in range(3):", "indent": 0},
            {"id": "2", "text": "print(i)", "indent": 1},
            {"id": "9", "text": "distractor"},
        ],
        "correct_order": ["1", "2"],
        "explanation": "Loop body is indented.",
    },
)
ECHO = json.dumps([{"stdin": "1", "stdout": "1"}, {"stdin": "2", "stdout": "2"}])
CODING = _q(QuestionType.CODING, {"tests": json.loads(ECHO)})
CODING_TESTS_COLUMN = _q(QuestionType.DEBUGGING, {}, tests=ECHO)
ASSERTS = _q(
    QuestionType.CODE_COMPLETION,
    {"tests": [{"assert": "assert add(2, 3) == 5"}, {"assert": "assert add(-1, 1) == 0"}]},
)

CASES: list[tuple[str, Question, str]] = [
    # multiple choice
    ("mcq right", MCQ, "1"),
    ("mcq right padded", MCQ, "  1 "),
    ("mcq wrong", MCQ, "0"),
    ("mcq out of range", MCQ, "99"),
    ("mcq negative", MCQ, "-1"),
    ("mcq garbage", MCQ, "banana"),
    ("mcq empty", MCQ, ""),
    ("mcq two indices", MCQ, "0,1"),
    ("mcq float", MCQ, "1.0"),
    ("mcq blank explanation", MCQ_BLANK_EXPLANATION, "0"),
    # true / false
    ("tf right", TF, "false"),
    ("tf right caps", TF, " FALSE "),
    ("tf wrong", TF, "true"),
    ("tf garbage", TF, "maybe"),
    ("tf index", TF, "1"),
    ("tf empty", TF, ""),
    # output prediction
    ("output right", OUTPUT, "1"),
    ("output right newline", OUTPUT, "1\n"),
    ("output crlf", OUTPUT, "1\r\n"),
    ("output two newlines", OUTPUT, "1\n\n"),
    ("output wrong", OUTPUT, "2"),
    ("output case", OUTPUT, " 1"),
    # parsons
    ("parsons newline right", PARSONS, "1\n    2"),
    ("parsons tab indent", PARSONS, "1\n\t2"),
    ("parsons comma no indent", PARSONS, "1,2"),
    ("parsons wrong order", PARSONS, "2\n    1"),
    ("parsons wrong indent", PARSONS, "1\n2"),
    ("parsons distractor", PARSONS, "1\n    2\n9"),
    ("parsons empty", PARSONS, ""),
    # executable
    ("coding all pass", CODING, "print(input())"),
    ("coding half pass", CODING, "print(1)"),
    ("coding crash", CODING, "raise ValueError('boom')"),
    ("coding syntax error", CODING, "print("),
    ("coding empty", CODING, "   "),
    ("coding tests column", CODING_TESTS_COLUMN, "print(input())"),
    ("asserts pass", ASSERTS, "def add(a, b):\n    return a + b"),
    ("asserts one fails", ASSERTS, "def add(a, b):\n    return abs(a) + b"),
]


#: Each run writes its program to a fresh temporary folder, whose random name appears in a
#: traceback; two runs of the *old* scorer differ there too, so it is blanked before comparing.
_TEMP_DIR = re.compile(r"tmp[a-z0-9_]{6,}", re.IGNORECASE)


def _comparable(scored) -> tuple:
    detail = _TEMP_DIR.sub("tmp…", scored.detail) if scored.detail else scored.detail
    return (scored.score, scored.passed_tests, scored.total_tests, detail)


@pytest.mark.parametrize(("name", "question", "answer"), CASES, ids=[case[0] for case in CASES])
def test_new_path_matches_the_old_scorer(name: str, question: Question, answer: str) -> None:
    old = grading_oracle.score_answer(question, answer)
    new = score_answer(question, answer)
    assert _comparable(new) == _comparable(old), name


def test_a_timeout_scores_the_same() -> None:
    question = _q(QuestionType.CODING, {"tests": [{"stdin": "", "stdout": "x"}]})
    old = grading_oracle.score_answer(question, "while True: pass")
    new = score_answer(question, "while True: pass")
    assert (new.score, new.passed_tests, new.total_tests) == (
        old.score,
        old.passed_tests,
        old.total_tests,
    )


UNMARKABLE = [
    _q(QuestionType.MULTIPLE_CHOICE, {"options": ["a"], "correct_option_index": 5}),
    _q(QuestionType.MULTIPLE_CHOICE, {"options": ["a", "b"]}),
    _q(QuestionType.TRUE_FALSE, {}),
    _q(QuestionType.OUTPUT_PREDICTION, {}),
    _q(QuestionType.PARSONS, {"blocks": [{"id": "1"}], "correct_order": ["1"]}),
    _q(QuestionType.CODING, {}),
]


@pytest.mark.parametrize("question", UNMARKABLE)
def test_unmarkable_questions_still_raise(question: Question) -> None:
    with pytest.raises(DomainRuleError):
        grading_oracle.score_answer(question, "0")
    with pytest.raises(DomainRuleError):
        score_answer(question, "0")
