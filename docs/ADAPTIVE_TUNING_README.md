# Adaptive Parameter Tuning

This note records how the current adaptive-training defaults were chosen.

## Final default values

These are the values now set in code:

- `p_init = 0.10`
- `p_learn = 0.03`
- `p_guess = 0.30`
- `p_slip = 0.05`
- `LOW_MASTERY_CEILING = 0.45`
- `MEDIUM_MASTERY_CEILING = 0.85`
- `WEAKNESS_LEARNING_RATE = 0.15`
- `MIN_SUBTOPIC_WEAKNESS = 0.05`

Code locations:

- `app/domain/mastery.py`
- `app/adaptive/state.py`

## How these initial values were found

These are **simulator-tuned initial defaults**, not values fitted from real student logs.

On **August 18, 2026**, the defaults were chosen with the standalone script:

- `tune_adaptive_params.py`

That script runs an in-memory simulation of the adaptive loop using the same core mechanics as the
real engine:

- weakness-weighted roulette over subtopics
- mastery-banded difficulty selection
- BKT-style mastery updates
- moving-average weakness updates
- question reuse only after unseen questions are exhausted

## Simulated student archetypes

The search was run against several student types rather than one average student:

- `beginner`
- `advanced`
- `uneven`
- `careless`
- `guesser`
- `fast_learner`

Each archetype has hidden subtopic skill levels plus its own guess rate, slip rate and learning
rate. The adaptive engine does not see those values directly; it only sees the student's answers.

## Search objective

The search did **not** optimize for maximum percent correct. That would bias the system toward
serving easier questions.

Instead, the objective was a robust score that rewards:

- appropriate challenge
- attention to genuinely weak subtopics
- steady learning progress
- limited early repetition

The script ranks parameter sets using:

```text
robust_score = 0.7 * mean_archetype_score + 0.3 * worst_archetype_score
```

That makes the chosen defaults work reasonably well across all archetypes rather than overfitting
to the easiest one to satisfy.

## Search process

The tuning pass was done in two stages.

1. A coarse grid search over all eight parameters.
2. A deeper validation run on the best finalists across multiple random seeds.

The full sweep consistently preferred:

- lower `p_init`
- much lower `p_learn`
- higher `p_guess`
- lower `p_slip`
- higher mastery thresholds
- slower weakness updates

`MIN_SUBTOPIC_WEAKNESS` was effectively tied across `0.03`, `0.05` and `0.08` in the validation
runs, so `0.05` was kept as the final default because it preserved exploration without making the
floor more aggressive than necessary.

## Intended behavior

Compared with the previous defaults, the tuned values are meant to behave like this:

- start students more cautiously
- promote students to harder questions more slowly
- treat one correct answer as weaker evidence of real mastery
- treat wrong answers as more meaningful evidence
- shift subtopic focus more smoothly after each answer
- keep mastered subtopics reachable without letting them dominate

In practice this means fewer premature jumps to `hard`, better handling of guessers, and less
erratic switching between subtopics.

## Re-running the tuner

To repeat or extend the search:

```powershell
.\.venv\Scripts\python.exe tune_adaptive_params.py
```

Useful flags:

- `--trials-per-archetype 12`
- `--questions-per-session 15`
- `--top 8`
- `--seed 2026`

If real student outcome data becomes available later, those logs should take precedence over the
simulated defaults recorded here.
