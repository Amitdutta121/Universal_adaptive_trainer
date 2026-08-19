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
- `TOPIC_ADVANCE_CEILING = 0.60`
- `WEAKNESS_LEARNING_RATE = 0.25`
- `MIN_SUBTOPIC_WEAKNESS = 0.05`

Code locations:

- `app/domain/mastery.py`
- `app/adaptive/state.py`

`MEDIUM_MASTERY_CEILING` and `TOPIC_ADVANCE_CEILING` are two different thresholds that happened to
share one value before sequential topic progression (ADR-047) existed. `MEDIUM_MASTERY_CEILING` is
still the HIGH-band boundary that requests a `HARD` question. `TOPIC_ADVANCE_CEILING` is when a
topic retires and the engine advances to the next one in curriculum position order. See "August 19,
2026" below for why they were split.

## How these initial values were found

These are **simulator-tuned initial defaults**, not values fitted from real student logs.

### August 18, 2026 — initial pass

The defaults were chosen with the standalone script `tune_adaptive_params.py`, which at the time ran
an in-memory simulation of the adaptive loop using the same core mechanics as the real engine:

- weakness-weighted roulette over subtopics
- mastery-banded difficulty selection
- BKT-style mastery updates
- moving-average weakness updates
- question reuse only after unseen questions are exhausted

### August 19, 2026 — re-tuned for sequential topic progression (ADR-047)

The adaptive engine changed to progress through the curriculum topic by topic rather than pooling
every topic's subtopics into one roulette (ADR-047). `tune_adaptive_params.py` did not model that at
all — it simulated one flat pool of subtopics under an implicit single topic — so the August 18
defaults were tuned against a mechanism the engine no longer runs.

The script was extended to simulate the real mechanism instead:

- two topics, three subtopics each, attempted in curriculum position order
- each topic tracks its own BKT mastery, starting fresh at `p_init`
- a topic retires once its mastery reaches `topic_advance_ceiling` and the roulette pool moves to
  the next topic's subtopics
- a session ends early, with its remaining question budget unused, once every topic has retired --
  mirroring `CurriculumCompletedError`
- a new `completion` score component (fraction of topics retired within the session's question
  budget) was added alongside challenge, targeting, progress and repeat, so the search can see
  whether a parameter set actually lets students finish the curriculum

The first re-run initially searched `medium_mastery_ceiling` as the *same* knob driving topic
advancement (the ADR-047 code inherited the shared threshold from the original design). That search
consistently wanted to lower it to ~0.70, which would also have lowered the `HARD`-difficulty
boundary as a side effect. Rather than accept that coupling, `topic_advance_ceiling` was split out as
an independent parameter, `medium_mastery_ceiling` was held fixed at 0.85 for this pass, and the
search was re-run. That decoupled search is what produced the `TOPIC_ADVANCE_CEILING = 0.60` and
`WEAKNESS_LEARNING_RATE = 0.25` defaults above -- see "Search process" below for the numbers.

## Simulated student archetypes

The search was run against several student types rather than one average student:

- `beginner`
- `advanced`
- `uneven` -- weak in topic 1, already strong in topic 2, to check the engine holds them in topic 1
  by that topic's own mastery rather than releasing them early because a later topic looks easy
- `careless`
- `guesser` -- low real skill but a high guess rate, to check BKT is not fooled into advancing a
  topic the student has not actually learned
- `fast_learner`

Each archetype has hidden subtopic skill levels plus its own guess rate, slip rate and learning
rate. The adaptive engine does not see those values directly; it only sees the student's answers.

## Search objective

The search did **not** optimize for maximum percent correct. That would bias the system toward
serving easier questions.

Instead, the objective was a robust score that rewards:

- appropriate challenge
- attention to genuinely weak subtopics, within the topic currently in reach
- steady learning progress
- limited early repetition
- actually advancing through the curriculum within the session's question budget (`completion`,
  added August 19, 2026 for sequential progression)

The script ranks parameter sets using:

```text
robust_score = 0.7 * mean_archetype_score + 0.3 * worst_archetype_score
```

That makes the chosen defaults work reasonably well across all archetypes rather than overfitting
to the easiest one to satisfy.

## Search process

### August 18, 2026

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

### August 19, 2026 — sequential progression re-tune

A coarse grid search (12 trials/archetype, 24 questions/session) with `topic_advance_ceiling` as its
own axis and `medium_mastery_ceiling` fixed at 0.85:

- `topic_advance_ceiling`: consistently `0.60` across the top results (`0.55` a close second) --
  down sharply from the pre-split 0.85, confirming that topic pacing and difficulty banding really
  do want different numbers
- `weakness_learning_rate`: consistently `0.25` across every top result -- up from `0.15`, because
  with the roulette now scoped to one topic's handful of subtopics at a time, the old rate left
  weakness too slow to reflect a recent run of answers
- `p_init`: no consistent signal once decoupled from the threshold (the top three results all keep
  it at `0.10`, ties with `0.25` follow immediately after) -- left unchanged
- `p_learn`, `p_guess`, `p_slip`, `LOW_MASTERY_CEILING`, `MIN_SUBTOPIC_WEAKNESS`: no change; the
  search kept these at their August 18 values throughout the top results

The robust-score gain over the pre-split defaults was modest (`0.429 -> 0.452`, roughly +5%) — this
was a single coarse pass over a simulator that had just been extended, not the deeper multi-seed
validation the August 18 numbers got. Treat `TOPIC_ADVANCE_CEILING` and `WEAKNESS_LEARNING_RATE` as
reasonable starting points, due for the same validation-pass treatment (or real student data) later.

## Intended behavior

Compared with the pre-ADR-047 defaults, the tuned values are meant to behave like this:

- start students more cautiously
- promote students to harder questions more slowly
- treat one correct answer as weaker evidence of real mastery
- treat wrong answers as more meaningful evidence
- shift subtopic focus more sharply after each answer, since only a few subtopics are ever live at
  once within the current topic
- keep mastered subtopics reachable without letting them dominate
- move on to the next topic well before mastery would be considered HIGH enough for a `HARD`
  question, so a fixed question budget actually reaches later topics

In practice this means fewer premature jumps to `hard` (now rare inside a topic's own request, since
the topic advances first), better handling of guessers, less erratic switching between subtopics, and
more students reaching later topics within a session.

## Re-running the tuner

To repeat or extend the search:

```powershell
.\.venv\Scripts\python.exe tune_adaptive_params.py
```

Useful flags:

- `--trials-per-archetype 12`
- `--questions-per-session 24` (two topics x three subtopics needs more budget than the old
  single-topic, 15-question default)
- `--top 8`
- `--seed 2026`

If real student outcome data becomes available later, those logs should take precedence over the
simulated defaults recorded here.
