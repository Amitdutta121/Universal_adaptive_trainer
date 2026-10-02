"""Every shipped prompt, rendered from fixed inputs (phase 2, S0).

    .\\.venv\\Scripts\\python.exe -m scripts.show_prompts            # print them
    .\\.venv\\Scripts\\python.exe -m scripts.show_prompts --write    # refresh the golden file

The golden file (``tests/golden/python_prompts.json``) was captured from the code before any
phase-2 change; ``tests/test_golden_prompts.py`` requires the Python course's prompts to stay
byte-identical to it. Refresh it only for a deliberate prompt change, and say so in the commit.
No database, no LLM: every input below is a fixture.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden" / "python_prompts.json"

sys.path.insert(0, str(ROOT))

from app.curriculum.drafting import DRAFT_SYSTEM_PROMPT, DraftBrief, draft_user_prompt  # noqa: E402
from app.domain.enums import Difficulty, JudgeMetricId, QuestionType  # noqa: E402
from app.evaluation import judge_learning  # noqa: E402
from app.evaluation.prompts import (  # noqa: E402
    RUBRIC_VERSION,
    SYSTEM_PROMPT_FOR,
    JudgeContext,
    build_user_prompt,
)
from app.generation import prompts as generation_prompts  # noqa: E402
from app.generation.principles import COMMON_SYSTEM  # noqa: E402
from app.generation.spec import QuestionSpec  # noqa: E402
from app.personalization import instructions  # noqa: E402

#: The seven types shipped before phase 2 -- the golden file covers exactly these.
PYTHON_TYPES = (
    QuestionType.MULTIPLE_CHOICE,
    QuestionType.TRUE_FALSE,
    QuestionType.OUTPUT_PREDICTION,
    QuestionType.CODE_COMPLETION,
    QuestionType.DEBUGGING,
    QuestionType.PARSONS,
    QuestionType.CODING,
)

_TAXONOMY = SimpleNamespace(
    topics=[
        SimpleNamespace(
            id=1,
            name="Loops",
            subtopics=[
                SimpleNamespace(id=11, name="for loops", description="Iterating a sequence."),
                SimpleNamespace(id=12, name="while loops", description=None),
            ],
        ),
        SimpleNamespace(id=2, name="Functions", subtopics=[]),
    ]
)
_SECTION = "A for loop runs its body once per item:\n\nfor x in [1, 2]:\n    print(x)"
_CITATION = "Sample Book, ch. 3, p. 41"
_JUDGE_CONTEXT = JudgeContext(
    question_artifact={"prompt": "What does the loop print?", "expected_output": "1\n2"},
    source_sections=[{"section_id": 5, "text": _SECTION}],
    taxonomy=[{"topic_id": 1, "name": "Loops", "subtopics": [{"id": 11, "name": "for loops"}]}],
    claimed_taxonomy={"topic_id": 1, "subtopic_ids": [11]},
    requested_difficulty="easy",
    requested_question_type="output_prediction",
)


def collect_prompts() -> dict[str, str]:
    """Name -> exact prompt text, for every prompt the app ships."""
    out: dict[str, str] = {}
    taxonomy = generation_prompts.render_taxonomy(_TAXONOMY)  # type: ignore[arg-type]
    out["generation.system"] = COMMON_SYSTEM
    out["generation.classification"] = generation_prompts.CLASSIFICATION_INSTRUCTION
    out["generation.taxonomy"] = taxonomy
    for question_type in PYTHON_TYPES:
        instruction = generation_prompts.base_type_instruction(question_type)
        out[f"generation.type_instruction.{question_type.value}"] = instruction
        out[f"generation.type_fingerprint.{question_type.value}"] = (
            generation_prompts.instruction_fingerprint(instruction)
        )
        spec = QuestionSpec(
            curriculum_version_id=1,
            question_type=question_type,
            difficulty=Difficulty.MEDIUM,
            source_section_ids=[5],
        )
        for label, feedback in (("plain", None), ("feedback", "Make the loop count down.")):
            system, user = generation_prompts.build_prompt(
                spec,
                section_text=_SECTION,
                citation=_CITATION,
                taxonomy=taxonomy,
                instructor_feedback=feedback,
            )
            out[f"generation.user.{question_type.value}.{label}"] = user
            out[f"generation.system_returned.{question_type.value}.{label}"] = system
    for metric in JudgeMetricId:
        out[f"judge.system.{metric.value}"] = SYSTEM_PROMPT_FOR[metric]
        out[f"judge.user.{metric.value}"] = build_user_prompt(metric, _JUDGE_CONTEXT)
    out["judge.rubric_version"] = RUBRIC_VERSION
    out["judge_learning.system"] = judge_learning.SYSTEM
    out["judge_learning.rendered"] = judge_learning.render_judge_prompt(
        SYSTEM_PROMPT_FOR[JudgeMetricId.ISSUES],
        [judge_learning.LearnedJudgeRule(rule="Accept prints with a trailing space.")],
    )
    out["personalization.system"] = instructions.SYSTEM
    out["taxonomy_draft.system"] = DRAFT_SYSTEM_PROMPT
    out["taxonomy_draft.user"] = draft_user_prompt(
        DraftBrief(
            title="Intro mechanics",
            description="Forces and motion for first-year students.",
            audience="First-year undergraduates",
            must_cover="Newton's laws",
            leave_out="Relativity",
        )
    )
    return out


def main(argv: list[str]) -> int:
    prompts = collect_prompts()
    if "--write" in argv:
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(
            json.dumps(prompts, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {len(prompts)} prompts to {GOLDEN.relative_to(ROOT)}")
        return 0
    for name, text in prompts.items():
        print(f"===== {name}\n{text}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
