r"""Simple grid-search tuner for the adaptive-training defaults.

This script is intentionally standalone and in-memory:

- no database;
- no web app;
- no frozen question sets;
- no generated questions.

It simulates a few student archetypes against the same core mechanics the
adaptive engine uses:

- weakness-weighted roulette over subtopics;
- mastery-banded difficulty selection;
- candidate ranking with reuse allowed;
- BKT-like mastery updates;
- moving-average weakness updates.

Edit `SEARCH_SPACE` and `ARCHETYPES` below, then run:

    .\.venv\Scripts\python.exe tune_adaptive_params.py

The search objective is robust rather than optimistic:

    robust_score = 0.7 * mean_archetype_score + 0.3 * worst_archetype_score

That pushes the chosen defaults toward "works reasonably well for everyone"
rather than "works very well for one archetype".
"""

from __future__ import annotations

import argparse
import math
import random
from dataclasses import dataclass
from itertools import product
from statistics import fmean

from app.adaptive.selection import (
    Candidate,
    choose_subtopic,
    difficulty_fallback_order,
    rank_candidates,
)
from app.adaptive.state import MIN_SUBTOPIC_WEAKNESS, WEAKNESS_LEARNING_RATE
from app.domain.enums import Difficulty
from app.domain.mastery import (
    DEFAULT_BKT_PARAMETERS,
    INITIAL_SUBTOPIC_WEAKNESS,
    LOW_MASTERY_CEILING,
    MEDIUM_MASTERY_CEILING,
)
from app.domain.questions import DEFAULT_PRIORITY, LOWEST_PRIORITY

TARGET_CORRECT_PROBABILITY = 0.70
SUBTOPICS = 3


@dataclass(frozen=True)
class TuningParameters:
    """Adaptive parameters under search."""

    p_init: float
    p_learn: float
    p_guess: float
    p_slip: float
    low_mastery_ceiling: float
    medium_mastery_ceiling: float
    weakness_learning_rate: float
    min_subtopic_weakness: float

    def summary(self) -> str:
        return (
            f"p_init={self.p_init:.2f}, p_learn={self.p_learn:.2f}, "
            f"p_guess={self.p_guess:.2f}, p_slip={self.p_slip:.2f}, "
            f"bands=({self.low_mastery_ceiling:.2f}, {self.medium_mastery_ceiling:.2f}), "
            f"weak_rate={self.weakness_learning_rate:.2f}, "
            f"weak_floor={self.min_subtopic_weakness:.2f}"
        )


CURRENT_DEFAULTS = TuningParameters(
    p_init=DEFAULT_BKT_PARAMETERS.p_init,
    p_learn=DEFAULT_BKT_PARAMETERS.p_learn,
    p_guess=DEFAULT_BKT_PARAMETERS.p_guess,
    p_slip=DEFAULT_BKT_PARAMETERS.p_slip,
    low_mastery_ceiling=LOW_MASTERY_CEILING,
    medium_mastery_ceiling=MEDIUM_MASTERY_CEILING,
    weakness_learning_rate=WEAKNESS_LEARNING_RATE,
    min_subtopic_weakness=MIN_SUBTOPIC_WEAKNESS,
)


# Edit these ranges first. Keep them coarse at the start.
SEARCH_SPACE: dict[str, list[float]] = {
    "p_init": [0.10, CURRENT_DEFAULTS.p_init, 0.25],
    "p_learn": [0.05, 0.10, CURRENT_DEFAULTS.p_learn],
    "p_guess": [CURRENT_DEFAULTS.p_guess],
    "p_slip": [CURRENT_DEFAULTS.p_slip],
    "low_mastery_ceiling": [0.35, 0.45],
    "medium_mastery_ceiling": [0.70, 0.80],
    "weakness_learning_rate": [0.15, 0.25, CURRENT_DEFAULTS.weakness_learning_rate],
    "min_subtopic_weakness": [0.03, CURRENT_DEFAULTS.min_subtopic_weakness, 0.08],
}


@dataclass(frozen=True)
class Archetype:
    """One kind of hidden student."""

    name: str
    skills: tuple[float, ...]
    guess: float
    slip: float
    learn_rate: float
    fatigue_per_question: float = 0.0


ARCHETYPES: tuple[Archetype, ...] = (
    Archetype("beginner", (0.20, 0.25, 0.22), guess=0.18, slip=0.08, learn_rate=0.05),
    Archetype("advanced", (0.85, 0.88, 0.82), guess=0.08, slip=0.04, learn_rate=0.02),
    Archetype("uneven", (0.20, 0.82, 0.78), guess=0.15, slip=0.08, learn_rate=0.06),
    Archetype("careless", (0.78, 0.80, 0.76), guess=0.08, slip=0.20, learn_rate=0.03),
    Archetype("guesser", (0.20, 0.25, 0.18), guess=0.30, slip=0.08, learn_rate=0.03),
    Archetype("fast_learner", (0.40, 0.45, 0.35), guess=0.15, slip=0.07, learn_rate=0.10),
)


@dataclass
class SyntheticQuestion:
    """One synthetic question in the in-memory bank."""

    question_id: int
    subtopic_id: int
    difficulty: Difficulty
    priority: int = DEFAULT_PRIORITY
    times_used: int = 0


@dataclass
class SimulatedStudent:
    """Hidden student state that the adaptive engine cannot see directly."""

    skills: list[float]
    guess: float
    slip: float
    learn_rate: float
    fatigue_per_question: float

    def probability_correct(
        self,
        *,
        subtopic_id: int,
        difficulty: Difficulty,
        question_index: int,
    ) -> float:
        """Return the hidden chance of success for one served question."""
        skill = self.skills[subtopic_id - 1]
        target = {
            Difficulty.EASY: 0.30,
            Difficulty.MEDIUM: 0.60,
            Difficulty.HARD: 0.85,
        }[difficulty]
        signal = 1.0 / (1.0 + math.exp(-8.0 * (skill - target)))
        probability = self.guess + (1.0 - self.guess - self.slip) * signal
        probability -= self.fatigue_per_question * question_index
        return clamp(probability, 0.0, 1.0)

    def learn(self, *, subtopic_id: int, difficulty: Difficulty, correct: bool) -> None:
        """Update the hidden ground-truth skill after one attempt."""
        skill = self.skills[subtopic_id - 1]
        difficulty_factor = {
            Difficulty.EASY: 0.70,
            Difficulty.MEDIUM: 1.00,
            Difficulty.HARD: 0.80,
        }[difficulty]
        outcome_factor = 1.00 if correct else 0.35
        gain = self.learn_rate * difficulty_factor * outcome_factor * (1.0 - skill)
        self.skills[subtopic_id - 1] = clamp(skill + gain, 0.0, 1.0)


@dataclass(frozen=True)
class SessionResult:
    """Metrics for one synthetic training run."""

    challenge: float
    targeting: float
    progress: float
    repeat_score: float
    observed_accuracy: float
    overall: float


@dataclass(frozen=True)
class EvaluationResult:
    """Aggregate metrics for one parameter set across many archetypes."""

    params: TuningParameters
    robust_score: float
    mean_score: float
    worst_score: float
    worst_name: str
    challenge: float
    targeting: float
    progress: float
    repeat_score: float
    observed_accuracy: float
    archetype_scores: dict[str, float]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def mastery_to_difficulty(p_known: float, params: TuningParameters) -> Difficulty:
    if p_known < params.low_mastery_ceiling:
        return Difficulty.EASY
    if p_known < params.medium_mastery_ceiling:
        return Difficulty.MEDIUM
    return Difficulty.HARD


def evidence_posterior(p_known: float, *, correct: bool, params: TuningParameters) -> float:
    if correct:
        likely_known = p_known * (1.0 - params.p_slip)
        likely_unknown = (1.0 - p_known) * params.p_guess
    else:
        likely_known = p_known * params.p_slip
        likely_unknown = (1.0 - p_known) * (1.0 - params.p_guess)
    total = likely_known + likely_unknown
    if total <= 0.0:
        return p_known
    return likely_known / total


def update_mastery(p_known: float, score: float, params: TuningParameters) -> float:
    fraction = clamp(score / 100.0, 0.0, 1.0)
    correct = evidence_posterior(p_known, correct=True, params=params)
    wrong = evidence_posterior(p_known, correct=False, params=params)
    posterior = fraction * correct + (1.0 - fraction) * wrong
    learned = posterior + (1.0 - posterior) * params.p_learn
    return clamp(learned, 0.0, 1.0)


def update_weakness(weakness: float, score: float, params: TuningParameters) -> float:
    implied = 1.0 - clamp(score / 100.0, 0.0, 1.0)
    moved = weakness + params.weakness_learning_rate * (implied - weakness)
    return clamp(moved, params.min_subtopic_weakness, INITIAL_SUBTOPIC_WEAKNESS)


def build_bank(*, subtopics: int, questions_per_cell: int) -> list[SyntheticQuestion]:
    question_id = 1
    bank: list[SyntheticQuestion] = []
    for subtopic_id in range(1, subtopics + 1):
        for difficulty in Difficulty:
            for _ in range(questions_per_cell):
                bank.append(
                    SyntheticQuestion(
                        question_id=question_id,
                        subtopic_id=subtopic_id,
                        difficulty=difficulty,
                    )
                )
                question_id += 1
    return bank


def serve_question(
    *,
    bank: list[SyntheticQuestion],
    answered_question_ids: set[int],
    weaknesses: dict[int, float],
    mastery: float,
    params: TuningParameters,
    rng: random.Random,
) -> tuple[SyntheticQuestion, int, Difficulty, Difficulty]:
    """Mirror the real selection loop in memory."""
    live_weights = dict(weaknesses)
    while live_weights:
        subtopic_id = choose_subtopic(live_weights, rng)
        requested = mastery_to_difficulty(mastery, params)
        for difficulty in difficulty_fallback_order(requested):
            rows = [
                question
                for question in bank
                if question.subtopic_id == subtopic_id and question.difficulty == difficulty
            ]
            if not rows:
                continue
            ranked = rank_candidates(
                [
                    Candidate(
                        question_id=question.question_id,
                        priority=question.priority,
                        times_used=question.times_used,
                        answered_by_student=question.question_id in answered_question_ids,
                    )
                    for question in rows
                ]
            )
            chosen_id = ranked[0].question_id
            chosen = next(question for question in rows if question.question_id == chosen_id)
            chosen.priority = LOWEST_PRIORITY
            chosen.times_used += 1
            return chosen, subtopic_id, requested, difficulty
        live_weights.pop(subtopic_id)
    raise RuntimeError("No synthetic question could be served.")


def challenge_score(probability_correct: float) -> float:
    """How close the served question was to the target challenge level."""
    distance = abs(probability_correct - TARGET_CORRECT_PROBABILITY)
    return clamp(1.0 - distance / 0.35, 0.0, 1.0)


def targeting_score(skills: list[float], served_subtopic_id: int) -> float:
    """Whether the algorithm favoured currently weaker subtopics."""
    needs = [1.0 - skill for skill in skills]
    served_need = needs[served_subtopic_id - 1]
    uniform_need = fmean(needs)
    max_need = max(needs)
    if max_need <= uniform_need + 1e-9:
        return 1.0
    scaled = (served_need - uniform_need) / (max_need - uniform_need)
    return clamp(scaled, 0.0, 1.0)


def progress_score(initial_skills: list[float], final_skills: list[float]) -> float:
    initial_mean = fmean(initial_skills)
    final_mean = fmean(final_skills)
    headroom = max(1.0 - initial_mean, 1e-9)
    return clamp((final_mean - initial_mean) / headroom, 0.0, 1.0)


def instantiate(archetype: Archetype) -> SimulatedStudent:
    return SimulatedStudent(
        skills=list(archetype.skills),
        guess=archetype.guess,
        slip=archetype.slip,
        learn_rate=archetype.learn_rate,
        fatigue_per_question=archetype.fatigue_per_question,
    )


def run_session(
    *,
    archetype: Archetype,
    params: TuningParameters,
    questions_per_session: int,
    questions_per_cell: int,
    seed: int,
) -> SessionResult:
    student = instantiate(archetype)
    initial_skills = list(student.skills)
    bank = build_bank(subtopics=len(student.skills), questions_per_cell=questions_per_cell)
    answered_question_ids: set[int] = set()
    weaknesses = dict.fromkeys(range(1, len(student.skills) + 1), INITIAL_SUBTOPIC_WEAKNESS)
    mastery = params.p_init
    rng = random.Random(seed)

    challenge_scores: list[float] = []
    targeting_scores: list[float] = []
    observed_scores: list[float] = []
    repeats = 0

    for question_index in range(questions_per_session):
        question, subtopic_id, _requested, served = serve_question(
            bank=bank,
            answered_question_ids=answered_question_ids,
            weaknesses=weaknesses,
            mastery=mastery,
            params=params,
            rng=rng,
        )
        if question.question_id in answered_question_ids:
            repeats += 1

        probability = student.probability_correct(
            subtopic_id=subtopic_id,
            difficulty=served,
            question_index=question_index,
        )
        challenge_scores.append(challenge_score(probability))
        targeting_scores.append(targeting_score(student.skills, subtopic_id))

        correct = rng.random() < probability
        score = 100.0 if correct else 0.0
        observed_scores.append(score / 100.0)

        mastery = update_mastery(mastery, score, params)
        weaknesses[subtopic_id] = update_weakness(weaknesses[subtopic_id], score, params)
        answered_question_ids.add(question.question_id)
        student.learn(subtopic_id=subtopic_id, difficulty=served, correct=correct)

    repeat_component = 1.0 - repeats / questions_per_session
    progress_component = progress_score(initial_skills, student.skills)
    challenge_component = fmean(challenge_scores)
    targeting_component = fmean(targeting_scores)
    observed_accuracy = fmean(observed_scores)

    overall = (
        0.50 * challenge_component
        + 0.30 * targeting_component
        + 0.15 * progress_component
        + 0.05 * repeat_component
    )
    return SessionResult(
        challenge=challenge_component,
        targeting=targeting_component,
        progress=progress_component,
        repeat_score=repeat_component,
        observed_accuracy=observed_accuracy,
        overall=overall,
    )


def evaluate_parameter_set(
    *,
    params: TuningParameters,
    archetypes: tuple[Archetype, ...],
    trials_per_archetype: int,
    questions_per_session: int,
    questions_per_cell: int,
    base_seed: int,
) -> EvaluationResult:
    archetype_scores: dict[str, float] = {}
    challenge_scores: list[float] = []
    targeting_scores: list[float] = []
    progress_scores: list[float] = []
    repeat_scores: list[float] = []
    observed_accuracies: list[float] = []

    for archetype_index, archetype in enumerate(archetypes):
        runs: list[SessionResult] = []
        for trial in range(trials_per_archetype):
            seed = base_seed + archetype_index * 10_000 + trial
            result = run_session(
                archetype=archetype,
                params=params,
                questions_per_session=questions_per_session,
                questions_per_cell=questions_per_cell,
                seed=seed,
            )
            runs.append(result)

        archetype_scores[archetype.name] = fmean(run.overall for run in runs)
        challenge_scores.extend(run.challenge for run in runs)
        targeting_scores.extend(run.targeting for run in runs)
        progress_scores.extend(run.progress for run in runs)
        repeat_scores.extend(run.repeat_score for run in runs)
        observed_accuracies.extend(run.observed_accuracy for run in runs)

    mean_score = fmean(archetype_scores.values())
    worst_name = min(archetype_scores, key=archetype_scores.get)
    worst_score = archetype_scores[worst_name]
    robust_score = 0.70 * mean_score + 0.30 * worst_score

    return EvaluationResult(
        params=params,
        robust_score=robust_score,
        mean_score=mean_score,
        worst_score=worst_score,
        worst_name=worst_name,
        challenge=fmean(challenge_scores),
        targeting=fmean(targeting_scores),
        progress=fmean(progress_scores),
        repeat_score=fmean(repeat_scores),
        observed_accuracy=fmean(observed_accuracies),
        archetype_scores=archetype_scores,
    )


def parameter_grid() -> list[TuningParameters]:
    keys = list(SEARCH_SPACE)
    candidates: set[TuningParameters] = {CURRENT_DEFAULTS}
    for values in product(*(SEARCH_SPACE[key] for key in keys)):
        params = TuningParameters(**dict(zip(keys, values, strict=True)))
        if params.low_mastery_ceiling >= params.medium_mastery_ceiling:
            continue
        candidates.add(params)
    return sorted(
        candidates,
        key=lambda item: (
            item.p_init,
            item.p_learn,
            item.p_guess,
            item.p_slip,
            item.low_mastery_ceiling,
            item.medium_mastery_ceiling,
            item.weakness_learning_rate,
            item.min_subtopic_weakness,
        ),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials-per-archetype", type=int, default=12)
    parser.add_argument("--questions-per-session", type=int, default=15)
    parser.add_argument("--questions-per-cell", type=int, default=3)
    parser.add_argument("--top", type=int, default=8)
    parser.add_argument("--seed", type=int, default=2026)
    return parser.parse_args()


def print_result(label: str, result: EvaluationResult) -> None:
    print(label)
    print(
        f"  robust={result.robust_score:.3f}  mean={result.mean_score:.3f}  "
        f"worst={result.worst_score:.3f} ({result.worst_name})"
    )
    print(
        f"  challenge={result.challenge:.3f}  targeting={result.targeting:.3f}  "
        f"progress={result.progress:.3f}  repeat={result.repeat_score:.3f}  "
        f"accuracy={result.observed_accuracy:.3f}"
    )
    print(f"  {result.params.summary()}")


def main() -> int:
    args = parse_args()
    if any(len(archetype.skills) != SUBTOPICS for archetype in ARCHETYPES):
        raise ValueError(f"Every archetype must define exactly {SUBTOPICS} subtopic skills.")

    candidates = parameter_grid()
    print(f"Evaluating {len(candidates)} parameter sets...")
    print(f"Archetypes: {', '.join(archetype.name for archetype in ARCHETYPES)}")
    print()

    results = [
        evaluate_parameter_set(
            params=params,
            archetypes=ARCHETYPES,
            trials_per_archetype=args.trials_per_archetype,
            questions_per_session=args.questions_per_session,
            questions_per_cell=args.questions_per_cell,
            base_seed=args.seed,
        )
        for params in candidates
    ]
    results.sort(key=lambda result: (result.robust_score, result.mean_score), reverse=True)

    baseline = next(result for result in results if result.params == CURRENT_DEFAULTS)
    best = results[0]

    print_result("Current defaults", baseline)
    print()
    print_result("Best candidate", best)
    print(f"  delta_vs_defaults={best.robust_score - baseline.robust_score:+.3f}")
    print()

    print(f"Top {min(args.top, len(results))} parameter sets")
    for index, result in enumerate(results[: args.top], start=1):
        print(
            f"{index:>2}. robust={result.robust_score:.3f}  mean={result.mean_score:.3f}  "
            f"worst={result.worst_score:.3f} ({result.worst_name})  "
            f"{result.params.summary()}"
        )

    print()
    print("Best candidate by archetype")
    for name, score in sorted(best.archetype_scores.items()):
        print(f"  {name:<12} {score:.3f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
