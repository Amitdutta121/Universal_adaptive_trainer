"""Insert hand-made approved questions with figures into a course, and freeze them as a set (fig1).

    .\\.venv\\Scripts\\python.exe -m scripts.seed_figure_questions --course-id 9

Nothing generates figures yet (fig2/fig4), so this is how the figure flow is tried in a browser:
the questions show in the course's question bank and review, and the frozen set can be opened by
a student. Content is the AI-in-games set of the figure prototype
(``frontend/src/app/experiments/figure-questions/mock-ai-games.ts``); the computed figure is the
prototype's real ``grid-11.svg``, saved through the figure storage.

Uses the database and figure folder of the current settings (``.env``). Running it again adds
nothing: questions it already added to the course are skipped.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.domain.enums import Difficulty, QuestionStatus, QuestionType  # noqa: E402
from app.figures import figure_problems  # noqa: E402
from app.figures.storage import save_svg  # noqa: E402
from app.persistence.models import QuestionRow, QuestionSubtopicRow  # noqa: E402
from app.persistence.repositories import (  # noqa: E402
    CourseRepository,
    CurriculumRepository,
    QuestionRepository,
    QuestionSetRepository,
    questions_in_course,
)

GENERATOR = "figure-seed"
GRID_SVG = ROOT / "frontend" / "public" / "experiments" / "figure-questions" / "grid-11.svg"

GAME_TREE = """flowchart TD
  A["A · MAX"] --> B["B · MIN"]
  A --> C["C · MIN"]
  A --> D["D · MIN"]
  B --> b1((3))
  B --> b2((12))
  B --> b3((8))
  C --> c1((2))
  C --> c2((4))
  C --> c3((6))
  D --> d1((14))
  D --> d2((5))
  D --> d3((2))"""
GAME_TREE_ALT = (
    "A game tree. MAX node A has three MIN children: B with leaves 3, 12, 8; "
    "C with leaves 2, 4, 6; D with leaves 14, 5, 2."
)

FSM = """flowchart LR
  Patrol -- sees player --> Chase
  Chase -- in range --> Attack
  Chase -- lost player --> Patrol
  Attack -- out of range --> Chase
  Attack -- low health --> Flee
  Chase -- low health --> Flee
  Flee -- healed --> Patrol"""
FSM_ALT = (
    "A state machine. Patrol goes to Chase on sees player. Chase goes to Attack on in range, "
    "to Patrol on lost player, to Flee on low health. Attack goes to Chase on out of range and "
    "to Flee on low health. Flee goes to Patrol on healed."
)

VISITS = {
    "type": "bar",
    "data": {
        "labels": ["a", "b", "c", "d"],
        "datasets": [{"label": "Visits", "data": [120, 410, 380, 90]}],
    },
    "x_title": "Root move",
    "y_title": "Visits",
}
VISITS_ALT = "Bar chart of visits per root move: a 120, b 410, c 380, d 90."

GRID_ALT = (
    "An 8 by 8 grid with dark wall cells, a start cell S and a goal cell G; the walls force a "
    "detour from the straight route."
)
GRID_CAPTION = "An 8 by 8 grid. Dark cells are walls."


def _diagram(source: str, alt: str, caption: str = "") -> dict[str, Any]:
    return {"kind": "diagram", "source": source, "alt": alt, "caption": caption}


def _chart(chart: dict[str, Any], alt: str, caption: str = "") -> dict[str, Any]:
    return {"kind": "chart", "chart": chart, "alt": alt, "caption": caption}


def _numeric(value: float, explanation: str) -> dict[str, Any]:
    return {
        "value": value,
        "unit": "",
        "relative_tolerance": 0.0,
        # Exact integers still need a non-zero absolute tolerance or the grader refuses to mark.
        "absolute_tolerance": 1e-6,
        "calculation": str(value),
        "explanation": explanation,
    }


def questions(grid_key: str) -> list[tuple[QuestionType, str, dict[str, Any]]]:
    """``(type, prompt, content without the prompt)`` for every seeded question."""
    grid = {"kind": "computed", "file": grid_key, "alt": GRID_ALT, "caption": GRID_CAPTION}
    return [
        (
            QuestionType.MULTIPLE_CHOICE,
            "Alpha-beta search visits the children left to right. "
            "Which leaves are never evaluated?",
            {
                "options": ["4 and 6 under C", "12 and 8 under B", "5 and 2 under D", "None"],
                "correct_option_index": 0,
                "explanation": "After B, alpha = 3. C's first leaf is 2 ≤ 3, so C cannot beat B "
                "and 4, 6 are pruned. D's leaves 14 and 5 stay above 3, so all of D is searched.",
                "figure": _diagram(GAME_TREE, GAME_TREE_ALT, "Leaves are utilities for MAX."),
            },
        ),
        (
            QuestionType.NUMERIC_RESPONSE,
            "How many more simulations went through the most-visited root move than through "
            "the least-visited one?",
            {
                **_numeric(320, "b has the most visits (410) and d the fewest (90): 410 - 90."),
                "figure": _chart(VISITS, VISITS_ALT, "Visits per root move after 1,000 runs."),
            },
        ),
        (
            QuestionType.TRUE_FALSE,
            "The agent moves up, down, left or right one cell at a time and cannot enter dark "
            "cells. The shortest path from S to G takes 22 moves.",
            {
                "correct_answer": True,
                "explanation": "The walls force 8 moves more than the Manhattan distance of 14.",
                "figure": grid,
            },
        ),
        (
            QuestionType.MULTIPLE_CHOICE,
            "After 1,000 simulations, MCTS plays the most-visited move (robust child). "
            "Which move does it play?",
            {
                "options": ["Move a", "Move b", "Move c", "Move d"],
                "correct_option_index": 1,
                "explanation": "Move b has the most visits (410).",
                "figure": _chart(VISITS, VISITS_ALT, "Visits per root move."),
            },
        ),
        (
            QuestionType.NUMERIC_RESPONSE,
            "The agent moves up, down, left or right one cell at a time and cannot enter dark "
            "cells. How many moves does the shortest path from S to G take?",
            {
                **_numeric(22, "The walls force 8 moves more than the Manhattan distance of 14."),
                "figure": grid,
            },
        ),
        (
            QuestionType.TRUE_FALSE,
            "An enemy in Patrol with low health that sees the player goes straight to Flee.",
            {
                "correct_answer": False,
                "explanation": "Patrol has no edge to Flee. Seeing the player moves it to Chase; "
                "low health then moves it to Flee.",
                "figure": _diagram(FSM, FSM_ALT),
            },
        ),
    ]


def seed(session: Session, course_id: int) -> tuple[list[int], int | None]:
    """Add the figure questions to ``course_id``; returns the new question ids and set id."""
    CourseRepository(session).get(course_id)
    curriculum = CurriculumRepository(session)
    version = curriculum.get_approved(course_id=course_id)
    if version is None:
        raise SystemExit(f"Course {course_id} has no approved curriculum to file questions under.")
    tree = curriculum.get_with_tree(version.id)
    topic = next((topic for topic in tree.topics if topic.subtopics), None)
    if topic is None:
        raise SystemExit(f"Curriculum version {version.id} has no subtopics.")
    subtopic = topic.subtopics[0]

    grid_key = save_svg(course_id, GRID_SVG.read_text(encoding="utf-8"))
    existing = set(
        session.scalars(
            select(QuestionRow.prompt).where(
                questions_in_course(course_id), QuestionRow.generator_name == GENERATOR
            )
        )
    )
    repository = QuestionRepository(session)
    added: list[int] = []
    for question_type, prompt, content in questions(grid_key):
        if prompt in existing:
            continue
        problems = figure_problems(content["figure"])
        if problems:
            raise SystemExit(f"Seed figure is invalid: {problems}")
        row = repository.add(
            QuestionRow(
                prompt=prompt,
                original_prompt=prompt,
                curriculum_version_id=version.id,
                topic_id=topic.id,
                question_type=question_type,
                difficulty=Difficulty.EASY,
                status=QuestionStatus.APPROVED,
                content={"prompt": prompt, **content},
                generator_name=GENERATOR,
                generator_version="1",
            )
        )
        session.add(QuestionSubtopicRow(question_id=row.id, subtopic_id=subtopic.id))
        added.append(row.id)
    set_id = None
    if added:
        frozen = QuestionSetRepository(session).create(
            label="Figure questions", question_ids=added, curriculum_version_id=version.id
        )
        set_id = frozen.id
    session.flush()
    return added, set_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--course-id", type=int, required=True)
    args = parser.parse_args(argv)

    from app.persistence.database import session_scope

    with session_scope() as session:
        added, set_id = seed(session, args.course_id)
    if not added:
        print(f"Course {args.course_id} already has the figure questions; nothing added.")
    else:
        print(f"Added questions {added} to course {args.course_id}; frozen as set {set_id}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
