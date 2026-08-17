# Judge alignment: design changes and experiments

**Date:** 2026-08-14 · **Model:** `openai/gpt-4o` via OpenRouter · **Spend:** $5.60 on the first budget (60c over, see E9b) + $2.79 of a second $3 budget for E10–E12 (the OpenRouter account is now empty)
· **Data:** `data/experiment/exp.db` (a copy; the live bank was never written to)

## Why this exists

ADR-039 makes each metric judge rewrite its own prompt from the cases it got wrong, and *assumes*
that this converges on the professor. Nothing measured whether it does. This document records the
design changes made to allow that question to be answered, the experiments actually run, and what
they found.

The short version: **the assumption is not supported, and two mechanisms in the current design are
demonstrably broken.** One of them explains the other.

---

## Part 1 — Design changes

Each change is grounded in published practice; the citation is the reason it was made, not
decoration.

| # | Change | Setting | Grounding |
|---|---|---|---|
| 1 | Freeze switches for each learning loop | `judge_learning_enabled`, `generator_learning_enabled` | A judge cannot be measured while the generator also moves. Standard experimental control; the earlier run had four generator instructions in four rounds |
| 2 | Minimum disagreements before a rewrite | `judge_repair_min_disagreements = 5` | Minibatch practice in GEPA / MIPROv2. The previous n=1 trigger produced a rule about one list comprehension |
| 3 | **Acceptance gate** — score the candidate, adopt only on a strict win | `judge_repair_gate_enabled`, `judge_repair_scoring_pairs = 8` | Universal in prompt optimisation: GEPA's minibatch acceptance, MIPROv2's validation search, OPRO's scored meta-prompt, ProTeGi's bandit selection, APE's select-and-resample. Propose-and-apply is mutation without selection |
| 4 | Balanced evidence — the rewriter now also sees cases the judge got right | — | Replay buffers in continual learning. Errors-only gives the model no base rate |
| 5 | Judge temperature pinned to 0 | `judge_temperature = 0.0` | Standard for LLM-as-judge. The client had been leaving the provider default of 1.0 |

Tests: **796 passing**, `ruff check` and `ruff format --check` clean.

### Deliberately not done, on literature grounds

- **Numeric 1–10 judge scores.** Poorly calibrated and heavily clustered; the four judges return a
  value plus a derived pass flag instead.
- **Rewriting the prompt from scratch each round.** ADR-033 already measured this losing earlier
  lessons; rules accumulate onto the shipped text instead.
- **Scoring a candidate on the cases it was trained on.** The ADR-035 held-out third is excluded
  from repair evidence and used only for scoring.
- **Claiming significance from single samples.** Everything below reports counts, not p-values.

---

## Part 2 — Experiments

### E1 — Is a judge verdict repeatable?

**Method.** 10 questions × 2 judges (`difficulty`, `issues`) × 3 repetitions, shipped prompts,
settings as they were (temperature unset → provider default 1.0). The verdict stored during the
earlier 20-question run gives a 4th sample per question.

**Result.**

| Window | Unstable verdicts |
|---|---|
| Within one batch of 3 | 1 / 20 (5%) |
| **Including the earlier run (4 samples)** | **4 / 20 (20%)** |

**Finding — the most important one in this document.** Question #65 is among the unstable verdicts.
#65 is the single disagreement that triggered the entire difficulty-judge rewrite in the earlier
experiment; re-run, the same prompt now fails it 3/3 where it passed it before.

The earlier 20-question run produced **4 disagreements**. The noise floor is **≈4 in 20**. The
disagreement signal that drives the whole learning loop is therefore inside the noise band.

### E1b — Does temperature 0 fix it?

**Method.** Identical to E1 with `temperature=0.0`.

**Result.** `difficulty` 0/10 unstable; `issues` **1/10 still unstable**.

**Finding.** Temperature 0 helps and is worth keeping, but hosted greedy decoding is not
deterministic. Repeatability must be bought with repeated sampling and a margin, not assumed.

### E2 — Baseline agreement per metric

**Method.** Re-analysis of the 20 labelled questions; no new calls. Per-metric agreement compares
the judge's own verdict against whether the professor cited one of *that judge's* reasons.

| Metric | Agreement |
|---|---|
| subtopic | 20/20 (100%) — but **never exercised**: zero objections and zero flags |
| difficulty | 19/20 (95%) |
| issues | **17/20 (85%)** |

Cell-level agreement over the same data was 90%, and hid the weakest judge entirely.

### E3 — Is reflective rewriting worth it?

**Method.** Three prompts for the `issues` judge, scored on the same 12 held-out labelled
questions, majority-of-3 voting at temperature 0. Arms:

- **A** shipped prompt (control)
- **B** the reflective rewrite the current design actually produced
- **D** shipped prompt + 8 labelled examples (the standard few-shot baseline)

**Result.**

| Arm | Agreement | Wrong on |
|---|---|---|
| A — shipped | 8/12 (67%) | 68, 71, 74, 76 |
| B — reflective rewrite | 8/12 (67%) | 68, 71, 74, 76 |
| D — few-shot, 8 examples | 8/12 (67%) | 68, 71, 74, 76 |

**Findings.**

1. **Identical error sets.** Not merely equal totals — all three arms fail on exactly the same four
   questions. Neither the rewrite nor eight worked examples changed a single decision.
2. **The rewrite failed on its own training case.** Arm B's learned rule was derived from #74, and
   B still gets #74 wrong. It did not fix the one example it was built from.
3. **The failures are systematic, not random.** The judge catches objective faults
   (`incorrect_answer`, #67) and misses subjective quality — `poor_distractors` (#76),
   `poor_wording` (#71), `not_pedagogically_useful` (#68) — plus one false alarm (#74). That is a
   capability gap, and prompt editing of this kind did not close it.
4. **This is why the gate now demands a strict win.** A tie does not mean "held its ground"; here a
   tie meant "changed nothing observable", while still costing a new `rubric_version` that
   fragments the evidence any later measurement must accumulate.

### E7 — Does auto-accept precision improve as the professor gives feedback?

This is the question that matters for deployment. The judge does not need to be perfect; it needs to
be **safe to trust when it says approved**. The measure is therefore *auto-accept precision* — of the
questions the judge gated `approved`, how many would the professor also approve — not overall
agreement.

**Method.** A second clean run: judge prompts and feedback history cleared, generator instructions
kept. 20 questions generated and reviewed **one at a time**, so the system could learn between
questions exactly as it would in use. Both learning loops enabled, new policy in force
(threshold 5, acceptance gate, temperature 0). Fresh sections, deliberately from a different part of
the textbook (exercises and miscellaneous chapters) than run 1.

**Result — precision did not improve; it collapsed.**

| After | Judge approved | Professor agreed | Precision |
|---|---|---|---|
| 5 reviews | 1 | 0 | 0% [0–79%] |
| 10 reviews | 2 | 0 | 0% [0–66%] |
| 15 reviews | 3 | 0 | 0% [0–56%] |
| 20 reviews | 3 | 0 | **0% [0–56%]** |

Cells: 15 `confirmed_bad`, 3 `missed`, 2 `false_alarm`. The professor approved 2 of 20 — and **both
were questions the judge had flagged**. On this section set the judge and the professor were, if
anything, anti-correlated.

**Result — no learning occurred at all.**

Zero judge prompts were rewritten across the 20 reviews. Disagreements accumulated to
`subtopic` 3, `issues` 3, `difficulty` 1 — none reached the threshold of 5. Under the corrected
policy the system **does not begin to learn within 20 reviews**. That is the intended behaviour
(E1 showed why learning from 1–2 cases is learning from noise), but it must be stated plainly:
safety was bought by not learning.

**Result — the two runs disagree violently.**

| Run | Sections | Auto-accept precision |
|---|---|---|
| 1 (Q57–76) | core teaching sections | 8/9 = **89%** |
| 2 (Q77–96) | exercise / miscellaneous sections | 0/3 = **0%** |
| **Pooled** | | **8/12 = 67% [95% CI 39–86%]** |

**Findings.**

1. **Auto-accept precision is not established at any usable level.** The honest pooled estimate is
   67% with a confidence interval from 39% to 86%. A triage filter needs to know it is above some
   floor; this data cannot place it above a coin flip.
2. **It is not stable across content.** 89% on core sections, 0% on exercise sections. Whatever the
   true figure is, it depends on where in the book the chunk comes from — so a single global
   precision number would be misleading even if it were tight.
3. **The professor's own approval rate moved with the sections too** (9/20 vs 2/20), so run 2's
   collapse is at least partly the generator producing worse questions from exercise sections, not
   only the judge misjudging them. Both explanations are bad news for auto-acceptance.
4. **The safeguards fired correctly.** No repair on 1–3 cases; no unscored adoption. Nothing broke.
   Nothing improved either.

### E9 — Does a stronger reasoning model fix it?

**Method.** The cleanest possible A/B: the **same 40 labelled questions, the same shipped prompts,
the same professor labels** — only the judge model changes, from `openai/gpt-4o` to
`openai/gpt-5.2`. Nothing was regenerated and nothing was relearned; this isolates model capability
from every other variable. Cost was $0.0031–0.0084 per call, the same order as gpt-4o, because the
cheaper input offsets the reasoning tokens.

**Result — triage performance.**

| Model | Approved | Precision | Review saved | Unsafe misses |
|---|---|---|---|---|
| gpt-4o, run 1 | 9/20 | 8/9 = 89% | 45% | 1 |
| **gpt-5.2, run 1** | 5/20 | **5/5 = 100%** [CI 57–100%] | 25% | **0** |
| gpt-4o, run 2 | 3/20 | 0/3 = 0% | 15% | 3 |
| **gpt-5.2, run 2** | **0/20** | — never approved | 0% | **0** |
| gpt-4o, pooled | 12/40 | **8/12 = 67%** | 30% | **4** |
| **gpt-5.2, pooled** | 5/40 | **5/5 = 100%** | 12.5% | **0** |

**Result — per-metric agreement got *worse*.**

| Metric | gpt-4o | gpt-5.2 |
|---|---|---|
| issues | 33/40 (83%) | 33/40 (83%) |
| subtopic | 34/40 (85%) | 29/40 (**73%**) |
| difficulty | 36/40 (90%) | 34/40 (85%) |

**Findings.**

1. **The stronger model is not more aligned — it is more conservative.** It agrees with the
   professor *less* often per metric, but every additional disagreement is a false alarm rather than
   a miss. For a triage filter that is the correct direction of error, and it is the direction
   ADR-034 says to prefer.
2. **It eliminated every unsafe miss across 40 questions**, including #65 — the exact question
   gpt-4o wrongly approved, and the one whose unstable verdict triggered the original judge rewrite.
3. **The cost is coverage.** Auto-acceptance fell from 30% of questions to 12.5%, and to zero on the
   weaker section set. A filter that approves nothing is perfectly safe and worth nothing.
4. **Model choice dominates prompt optimisation.** Swapping the model changed the safety profile
   completely; rewriting the prompt (E3) changed no decision at all. If effort is going anywhere, it
   should go here first.
5. **Still not established.** 5/5 has a confidence interval of 57–100%. It is consistent with 100%
   precision and equally consistent with worse than gpt-4o's 89%.

### E9b — Three judge models, identical data

**Method.** As E9, extended to `anthropic/claude-opus-5` on the same 20 run-1 questions with the
same prompts and the same labels.

**Result.**

| Model | Approved | Precision | Coverage | Unsafe | Missed on |
|---|---|---|---|---|---|
| gpt-4o | 9/20 | 8/9 = 89% [56–98%] | 45% | 1 | #65 |
| gpt-5.2 | 5/20 | 5/5 = **100%** [57–100%] | **25%** | **0** | — |
| **claude-opus-5** | **10/20** | 9/10 = 90% [60–98%] | **50%** | 1 | #68 |

Per-metric agreement (n=20): `issues` 85% for both gpt-4o and opus-5; `subtopic` 100% vs 95%;
`difficulty` 95% vs 90%.

**Findings.**

1. **The three models sit on a precision/coverage curve, not a quality ranking.** gpt-5.2 buys safety
   with coverage (0 unsafe, 25% saved). claude-opus-5 buys coverage with one miss (90% precision,
   50% saved). gpt-4o is dominated by opus-5 — same unsafe count, less coverage.
2. **They fail on different questions.** gpt-4o's miss is #65 (a medium-labelled one-method recall);
   opus-5's is #68 (a near-tautological item with absurd distractors). Only gpt-5.2 caught both. No
   single model dominates, which suggests an ensemble or a stricter gate rule would beat any of them
   alone.
3. **Per-metric agreement again fails to track triage quality.** opus-5 scores *lower* per metric
   than gpt-4o on two of three metrics while being the better triage filter. Agreement is the wrong
   objective; precision at a coverage target is the right one.
4. **None of the three is statistically separable.** All confidence intervals overlap heavily at
   n=20. This ranks nothing; it shows the shape of the trade-off and the size of the sample needed.

### Budget note — an overrun

The claude-opus-5 run was projected from a 2-question pilot at $0.0124/call and actually cost
$0.0245/call, because later questions carry longer code and the taxonomy-heavy subtopic payload.
Total spend reached **$5.60 against a $5 budget**. The lesson is procedural: cost per call is not
uniform across a question set, a 2-item pilot is too small to extrapolate from, and spend should be
re-checked mid-run rather than only at the ends.

### E10 — Which professor information is worth collecting?

The practical question: what should the review screen ask for, given that every extra field costs
the professor time?

**Measured effort per review**, from the 40 reviews actually written in these experiments:

| Channel | Cost |
|---|---|
| decision | 1 click |
| reason codes | 1.3 clicks |
| **free-text comment** | **180 chars ≈ 54 seconds of typing** |
| confirm the four judges' values | 4 clicks (not currently collected) |

**Method.** Train/test split across runs: build the judge prompt from run-1 reviews (Q57–76),
score on run-2 questions (Q77–96), which the judge has never seen. Difficulty judge, majority of 3,
temperature 0. Five arms, each adding one more channel of professor information.

**Result.**

| Arm | gpt-4o | gpt-5.2 |
|---|---|---|
| A — control, no professor information | 17/20 = 85% | 17/20 = 85% |
| B — decision only | 16/20 = 80% | — |
| C — + reason codes | 18/20 = **90%** | 15/20 = **75%** |
| D — + reason codes + comments | 18/20 = 90% | 17/20 = 85% |
| E — professor's stated rubric, no examples | 16/20 = 80% | — |

**Findings.**

1. **No channel reliably beats the control, and the sign flips between models.** Reason codes gained
   one question on gpt-4o and lost two on gpt-5.2. Every difference is 1–2 questions at n=20.
2. **Comments buy nothing.** C and D tie on gpt-4o. On gpt-5.2 comments only recover the ground that
   adding examples lost. Fifty-four seconds of typing per review, for no measurable gain to the
   judge. This is the clearest hassle saving available.
3. **Telling the judge only that the professor rejected something makes it worse** (B < A). A verdict
   without a reason is noise to a prompt.
4. **The professor's stated rubric did not help either** (E < A), which is a genuine surprise and the
   opposite of what the criteria-elicitation literature would predict. It is a fair statement of the
   standard I actually applied, and the judge still did worse with it.
5. Together with E3 — where neither a learned rewrite nor eight worked examples changed a single
   decision — the conclusion is consistent: **pushing professor information into the judge prompt
   does not improve the judge.**

**But one channel is not a prompt at all.** Counting what each channel yields as *supervision*
rather than as prompt text, over the same 40 questions:

| | Labels produced | Judge faults visible |
|---|---|---|
| today (reason codes, inferred attribution) | 39 | 9 of 17 |
| **confirm/correct each judge's value** | **120 (3.1×)** | **17 of 17** |

47% of real judge faults are invisible today because attribution is *inferred* from a
question-level verdict through a fixed reason→judge table. Asking the professor to confirm or
correct the value each judge already published — its proposed difficulty, its proposed subtopics,
its issue codes — makes the label *observed* instead. Three extra clicks, 3.1× the supervision, and
every fault becomes visible.

**The conclusion this points to:** professor information should feed **measurement and selection**,
not the prompt. Prompt-stuffing was measured not to work (E3, E10). Model and gate selection was
measured to work enormously (E9: unsafe misses 4/12 → 0/8). Better labels make selection possible;
they do not need to make the prompt longer.

### E11 — Does professor feedback improve the *generator*?

Every experiment above tested the judge. The generator was never isolated, and it is the more
plausible place for feedback to pay: its faults are *production constraints* a model can follow
("do not make the correct option the longest"), not acts of perception.

**Method.** Paired and blind. Eight fresh sections, each generated **twice** — once with the shipped
type instruction, once with the instruction learned from 60 professor reviews. No judges ran; the
professor is the measurement. The sixteen questions were shuffled, the arm hidden, and reviewed
under the same rubric before unblinding.

The learned instruction carried five rules, four of which target faults raised repeatedly in
earlier reviews: distractor plausibility and length, keyed-answer correctness, unintended multiple
correct answers, and irrelevant tags.

**Result.**

| Arm | Approved | Faults found |
|---|---|---|
| shipped | **5/8 (62%)** | poor_distractors 1, not_pedagogically_useful 1, too_easy 1 |
| learned (60 reviews) | **2/8 (25%)** | **ambiguous 3**, poor_distractors 1, too_easy 2 |

Paired by section: the learned instruction was better on **0** sections, worse on **3**, tied on 5.
Sign test on the three discordant pairs: one-sided p = 0.125 — suggestive, not significant.

**Finding — the rule produced the fault it was written to prevent.**

The learned instruction contains, verbatim: *"Reword the question prompt or options if multiple
answers are unintentionally correct, to prevent ambiguity."* The learned arm generated **three**
questions with multiple correct answers. The shipped arm generated **none**.

The mechanism is visible in the items. Another learned rule says *"ensure distractors are plausible
and of similar length to the correct answer"*. The generator followed it, and pushed the distractors
so close to the key that they crossed the line into being correct:

- one item where `strip()`, `strip('
')`, `map(str.strip, ...)` and `rstrip()` all strip trailing
  newlines — four correct options;
- one where `.read()` and `''.join([...])` both return the whole file as a string;
- one where two different loops both find the longest qualifying word.

Two learned rules interacted destructively, and the stronger one won. This is the concrete form of
a risk named in ADR-039's own caution about accumulated rules: nothing checks a rule against the
rules already present, and nothing tests whether the set as a whole still produces better output.

**Implication.** The generator has no acceptance gate. The judge got one in Part 1; the generator's
instruction is still adopted the moment it is written, unmeasured — the exact failure mode that made
judge repair drift. It needs the same treatment: propose, generate a sample, score against the
professor's labels, adopt only on a win.

### E12 — Would offline optimise-then-test work? (partial)

**The proposed architecture.** Collect reviews with all learning off; later the professor clicks
"optimise"; the labelled set is split train/test/val by group; a search (GEPA-style) proposes and
scores candidates; if the test score is poor, the professor is told to review more. This removes the
confounds E7 exposed and adds the selection step E3 showed is missing.

**Method.** A miniature version. Group split by section origin — train = run 1 (core sections,
Q57-76), test = run 2 (exercise sections, Q77-96) — a genuine group split rather than a random one.
Reflective mutation on the *training errors only* proposed three candidate prompts for the `issues`
judge. Each was scored on train; the winner was to be evaluated once on test.

**Result - incomplete.** The OpenRouter account exhausted its credits during candidate scoring, so
the test-set evaluation never ran. What completed:

| | Train score |
|---|---|
| shipped prompt | **15/20 (75%)** |
| best of 3 reflective candidates | **13/20 (65%)** |

**Findings.**

1. **All three candidates were worse than the shipped prompt on the data they were derived from.**
   Not worse on held-out data - worse on train. This is the fourth independent failure of prompt
   editing to improve a judge (E3, E10, E11, E12).
2. **The selection step worked exactly as designed.** A scored search would have rejected all three
   and shipped nothing. Under propose-and-apply (ADR-039 as built), the 13/20 candidate would have
   been adopted and made the judge worse. A direct, if small, demonstration of why the gate matters.
3. **The generalisation question is unanswered**, because no candidate won on train and so there was
   nothing to carry to test.
4. **This does not rule out GEPA.** Three samples of naive reflection is a far weaker search than a
   Pareto-guided loop with minibatch acceptance over hundreds of rollouts. What is established is
   that *naive reflection* fails here - already known - not that *no* prompt search can succeed.
5. **The professor-facing loop would have behaved correctly**: with test performance poor, it would
   have told the professor to review more. On this evidence that is the right instruction.

### E8 - Does credit assignment see the faults?

**Method.** For every metric-level fault in the 20 labelled questions, check whether the
attribution mechanism actually named that judge.

**Result.**

| Question | Judge at fault | Cell | Named? |
|---|---|---|---|
| 65 | difficulty | missed | yes |
| 71 | issues | confirmed_bad | **no** |
| 74 | issues | false_alarm | yes |
| 76 | issues | confirmed_bad | **no** |

**2 of 4 real faults were invisible: 50%.**

**Finding.** `_attributed_metrics` returns nothing for the agreeing cells. But a judge can be wrong
*inside* a cell where the two sides agree overall — the professor rejects for `poor_distractors`,
the difficulty judge correctly flags the item, so the cell is `confirmed_bad` and counts as
agreement, while the issues judge quietly missed the objection. Those cases never enter the
evidence pool.

This explains E3. The `issues` judge never improved partly because **it never received half its
error cases as evidence**.

---

## What was not run, and why

| Experiment | Why not |
|---|---|
| **E0 / E0b — benchmark + professor self-consistency** | Requires a human. I cannot blind myself to labels already in context, so a self-consistency figure from me would be meaningless. **This is the highest-value missing measurement**: it sets the ceiling any judge can reach, and without it "aligned with the professor" has no fixed target (see criteria drift, Shankar et al., UIST 2024) |
| E4 — evidence composition ablation | Needs a larger labelled set |
| E5 — batch-size sweep | Needs more rounds |
| E6 — coupled vs decoupled learning | Needs full regeneration; ~$2–3 |
| E7 — online longitudinal | Only meaningful after a configuration is chosen |

---

## The right way to read all of this

The judge is not meant to be perfect. It is a **triage filter**: when it says `approved`, the
question skips human review; otherwise it reaches the professor. So the deployment question is not
"does it agree with me" but **"when it says approved, can I trust it?"** — auto-accept precision —
together with how much review it saves.

By that measure: **precision is 8/12 = 67% [39–86%] across 40 reviewed questions, and it is not
stable across content (89% vs 0% between two runs).** Review saved would have been 45% in run 1 and
15% in run 2. There is no operating point here that can be recommended.

The two error types are not equal, and the design already encodes this (ADR-034). A `missed` ships
an unreviewed bad question; a `false_alarm` costs thirty seconds. Any future tuning should maximise
coverage subject to a precision floor, not maximise agreement.

## Conclusions

1. **There is no evidence the judge becomes progressively more aligned.** Per-metric agreement over
   the four earlier rounds went 100% → 93% → 93% → 87%, and the judge that declined had not changed.
   In the one-at-a-time run, auto-accept precision started at 0% and stayed there.
2. **The disagreement signal is inside the noise floor.** 20% verdict instability against
   4 disagreements per 20 questions. The rewrite that did happen was triggered by an unstable verdict.
3. **Reflective rewriting produced no measurable improvement**, and neither did few-shot. The
   remaining errors are a capability gap in subjective quality judgement.
4. **Half the evidence never reaches the learner** because faults inside agreeing cells are not
   attributed.
5. **Under the corrected policy the system does not begin learning within 20 reviews**, because no
   judge accumulated 5 disagreements. Safety was bought by not learning. That is the right trade
   given E1, but it means the loop needs far more feedback than expected before it does anything.
6. The design changes in Part 1 stop the known failure modes — n=1 triggers, unscored adoption,
   errors-only evidence, unpinned temperature — but they do not create alignment. They make its
   absence visible.

## Recommended next changes, in order

1. **Attribute faults in every cell, not only disagreeing ones.** Directly indicated by E8; the
   single highest-value fix, and the cheapest. *Not implemented here — found late, deserves its own
   change and its own tests.*
2. **Require a stable disagreement before it counts as evidence.** Confirm with a repeat call, or
   majority-of-3, before a verdict is allowed to trigger learning. Indicated by E1.
3. **Run E0 with the generator frozen** to obtain a real benchmark and your own self-consistency
   ceiling.
4. **Consider that `issues` may not be fixable by prompt editing.** E3 suggests splitting it into
   narrower judges (one for distractor quality, one for wording) rather than continuing to rewrite
   one prompt that is blind to both.
5. **Use the stronger judge model, and measure the coverage you are buying.** E9 shows gpt-5.2
   removes every unsafe miss at roughly half the coverage. Whether that trade is worth it is the
   professor's call, and it is a one-line configuration change rather than a learning loop.
6. **Tune the gate rule before tuning any prompt.** `approved` currently requires all four metrics to
   pass. Making it stricter — for example also requiring the difficulty judge to agree on the exact
   level, which E2 showed is the strongest of the four — trades coverage for precision. This is a
   decision rule over verdicts already stored, so the whole precision/coverage curve can be swept
   offline at zero API cost. Prompt rewriting costs money per attempt and, in E3, moved nothing.

## Limitations

- n = 40 labelled questions across two runs, one question type (`multiple_choice`), one textbook,
  two judge models. Auto-accept precision rests on just 12 auto-accepts.
- My rubric is strict about difficulty labels: an item whose demand is a full level below its label
  is rejected as `too_easy`. That drove a high rejection rate (29 of 40) and is the single largest
  influence on every figure here. A more permissive professor would see different numbers.
- I acted as the professor. My criteria may have drifted across rounds; I cannot rule this out, and
  E1's noise result means some of what looked like drift may have been the judge resampling.
- Arm B in E3 was trained on evidence overlapping the test set, which flatters it — and it still
  did not win.
- The `subtopic` judge is untested rather than validated.
- The experiment database inherits 8 review outcomes from an earlier session by the real user, so
  the difficulty judge's learned rules draw on two different professors.
