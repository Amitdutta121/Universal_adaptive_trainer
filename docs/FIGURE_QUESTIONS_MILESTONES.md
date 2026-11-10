# Figure questions — diagrams, charts and computed figures, for any subject

**Goal.** A question can carry a figure the student must read to answer it: a **diagram**
(Mermaid), a **chart** (Chart.js), or a **computed figure** (an SVG drawn by a program that also
computes the answer, PrairieLearn-style). It works for every course the app can hold, preset or
custom, because nothing in it names or branches on a subject. Grading does not change: a figure
is something the student reads, not a new way of answering.

**Evidence it is wanted and works.** `/experiments/figure-questions` (`frontend/src/app/experiments/ figure-questions/`) shows the student side for CS 681 AI in Games, intro Python, data science and
ML, with the real answer widgets. Its computed SVGs and keys are real output of a `generate(seed)`
matplotlib program (box plot, histogram, BFS on a grid), 8–13 KB each.

`start fig1` / `verify fig1`. Prefix `fig` because `MILESTONES.md` uses `m`, the generic-assessment
plan uses `g`/`T`/`S`, and the backlog's milestones are `f1`–`f11`.

---



## Universality rules (acceptance criteria for every milestone)

1. **No subject in the figure code.** Figure kinds, prompts, validators, renderers and the
  generator contract never name a subject, preset id or course. A test scans `app/figures/` and
   the figure prompt text for preset ids and subject words (like the `graders/` import scan).
2. **Figure kinds are defined once, like capabilities.** `app/assessment/catalog.py` gets
  `FIGURE_KINDS` (id, label, what it can show, in subject-neutral words). The boundary text
   (`app/curriculum/capabilities.py`) lists them from that table, so the course designer and agent
   learn about them for every course at once.
3. **A course gets figures from its material, not its subject.** Whether a style uses a figure,
  and which kind, is decided by the style drafter / course designer from the course's own
   subtopics and book (a tree, a process, a dataset, a grid, a cycle…). Subject presets may only add
   *example* figure styles, the way they already add example questions; a custom subject gets the
   same ability with no preset at all.
4. **Python behaviour is unchanged when no style asks for a figure.** `tests/golden/
  python_prompts.json` still matches byte for byte; figure instructions are added only to the
   spec of a style that has one.
5. **The computed-figure contract is subject-neutral.** A program prints one JSON object (prompt,
  figure SVG, answer fields of the question type, explanation). It uses only the executor's
   allowlisted packages (`EXECUTOR_PACKAGES`: numpy, pandas, matplotlib). The student never sees
   the program, so a biology or economics course can use it the same as a CS course.
6. **Proved on dissimilar subjects.** The cross-subject eval in fig5 must pass on at least four:
  intro Python (preset), a custom CS course (CS 681 AI in Games), a quantitative non-CS subject
   (statistics / data science), and a non-quantitative one (biology or economics).



## Decisions


| #   | Decision                                                                                                                                                                                                                                                                                               | Status                                                                               |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------ |
| D1  | A figure is an optional `figure` field on any question's content, not a new question type. Every type (choice, true/false, numeric, equation, output prediction…) can carry one.                                                                                                                       | YEs                                                                                  |
| D2  | Three kinds: `diagram` (Mermaid source), `chart` (Chart.js spec, extended with axis titles and x/y points), `computed` (SVG from a program).                                                                                                                                                           | Yes                                                                                  |
| D3  | Computed figures run **at generation time**, never while a student waits: K copies per question (K=3 to start), stored, one picked by the attempt's seed. PrairieLearn runs `generate()` live; precomputing keeps the sandbox off the serving path and lets judges review exactly what students see.   | Yes and make sure the LLm doesn't write programms that will take a long time to run. |
| D4  | Copies live in a new table `question_variants` (`question_id`, `seed`, `figure` JSON with the SVG, the type's answer fields, `course_id`), one Alembic revision. A question without a computed figure has no rows. Keeps 10–40 KB of SVG out of `questions.content_json`, which is read on every list. | save in files and point to it                                                        |
| D5  | Whether a style uses a figure is a style field, `figure: none | diagram | chart | computed`, chosen by the drafter from the material (rule 3).                                                                                                                                                         | Yes                                                                                  |
| D6  | Every figure carries a required text alternative (`alt`): read by screen readers, and the only view of a computed figure the text-only judges and blind solver get. A vision-model judge is later, not here.                                                                                           | Yes                                                                                  |
| D7  | SVGs are shown through `<img src="data:image/svg+xml…">`, never inlined, so a script in an SVG cannot run. Mermaid keeps `securityLevel: "strict"`.                                                                                                                                                    | Settled (prototype)                                                                  |


Recording D1–D7 is one new ADR in `docs/DECISIONS.md`, written in fig1.

## The contract (written in fig1, then frozen)

```python
# app/figures/schema.py — imported by app.question_types; imports only app.domain + pydantic
class DiagramFigure(BaseModel):  kind: Literal["diagram"];  source: str;  alt: str;  caption: str = ""
class ChartFigure(BaseModel):    kind: Literal["chart"];    chart: ChartSpec;  alt: str;  caption: str = ""
class ComputedFigure(BaseModel): kind: Literal["computed"]; file: str;  alt: str;  caption: str = ""  # storage key, D4
Figure = Annotated[DiagramFigure | ChartFigure | ComputedFigure, Field(discriminator="kind")]

def figure_problems(figure: Figure) -> list[str]   # validation, shared by tutorials and questions

# app/figures/storage.py — SVG files under settings.figure_dir (FIGURE_DIR); served by
# GET /api/figures/{course_id}/{sha256}.svg (public, image/svg+xml, nosniff, CSP default-src 'none')
def save_svg(course_id: int, svg: str) -> str   # "<course_id>/<sha256>.svg"
def read_svg(key: str) -> bytes
```

- `StudentView` (`app/question_types/base.py:39`) gains `figure: Figure | None`; one shared helper
in `question_types/_shared.py` passes it through for every type.
- The Mermaid validator moves from `app/tutorials/renderers.py:105-150` into `app/figures/`;
tutorials import it from there. This respects the import rule in `question_types/base.py:8-12`.
- Computed program output: `{"prompt", "figure": {"svg", "alt", "caption"}, <the type's draft fields>, "explanation"}`, validated by the type's own `draft_model`, so the answer key goes
through the same checks as an LLM-written draft.



## Milestones

Each has a visible deliverable, acceptance criteria and its validation command. One per session,
commit between.

### fig1 — The figure field, end to end, with hand-made questions

- **Deliverable:** a question with a `figure` in its content is served, shown, reviewed and
graded. Nothing generates figures yet; tests and a seed script insert them.
- **Changes:** `app/figures/` (schema, validators moved from tutorials), `StudentView.figure`,
`ServedQuestionOut.figure` (`web/routes/api/schemas.py:2280`), `pnpm run api:types`; frontend
`QuestionFigure` promoted from the experiment to `components/question-figure.tsx` and rendered by
a `QuestionBody` (prompt + figure) at every place a prompt is shown (student session, past-attempt
sheet, review, question detail, questions-for-chunk, style example card, agent tool renderer;
`[figure]` in the clamped browser preview). The numeric widget hides its Unit box and the
"m^3" hint when the question has no unit (seen in the prototype). ADR.
- **Accept:** (1) a choice, numeric and true/false question each with a diagram, chart and computed
figure renders on the student screen and in review; (2) `figure` never leaks answer fields
(whitelist test); (3) a broken Mermaid source fails `figure_problems`; (4) the subject-word scan
passes; (5) the Python golden prompts are unchanged.
- **Validate:** `pytest tests/test_figures*.py tests/test_question_setup_contracts.py`, `ruff`,
`pnpm tsc --noEmit`, `pnpm biome lint src`, `pnpm vitest run src/components`, and the flow driven
in Chrome.



### fig2 — Styles can ask for a figure; diagram and chart questions are generated

- **Deliverable:** a professor can approve a style that uses a diagram or chart, and generation
produces those questions for any course.
- **Changes:** `QuestionStyle.figure` and `ExampleQuestion.figure` (`styles/schema.py:77`),
`styles/drafting.py` system prompt, `styles/checks.py`, `styles/library.py:285`;
`FIGURE_KINDS` in the catalog and in `capabilities_text()`; `course_design/design.py`
(`STYLE_SYSTEM`); `response_model_for(type, style)` requires `figure` when the style has one;
the round-spec block in `generation/prompts.py:171` adds subject-neutral figure rules (the figure
is needed to answer; it does not show the answer; every node, axis and series is labelled; use a
flowchart for state machines, since `stateDiagram` overlaps labels); repair retry on
`figure_problems`.
- **Accept:** (1) the style drafter proposes a figure style for a subtopic whose material is a
structure or a dataset, in at least two unrelated subjects, and none for one that is not;
(2) generated figure questions pass the type's authoring checks; (3) Python golden prompts are
unchanged for styles without a figure.
- **Validate:** unit tests with a fake LLM; then a **paid** run (ask first) of a few questions per
figure style in two subjects.



### fig3 — Quality gates read the figure

- **Deliverable:** dedup, the blind solver and the judges see the figure, so figure questions are
held to the same bar as text ones.
- **Changes:** `retrieval/duplicates.py:68` `embed_text` adds the diagram source / chart data /
`alt`; `generation/solve.py:74` gives solvers the figure as text (Mermaid source, chart data,
`alt`); judge payloads (`evaluation/prompts.py:327`) include it; a new judge issue code
"the figure gives away the answer or does not match the question".
- **Accept:** (1) two questions with the same wording and different figures are not flagged as
duplicates; (2) a seeded mismatch (chart says 42, key says 45) is flagged by the solver;
(3) judge rubric version changes only for courses whose questions carry figures.
- **Validate:** `pytest` on dedup, solve and the judges with fixtures; no paid calls.



### fig4 — Computed figures (PrairieLearn-style), K copies per question

- **Deliverable:** a "computed" style makes the LLM write a `generate(seed)` program. The executor
runs it for K seeds, each copy is validated as a draft, and the student gets the copy picked by
their attempt's seed.
- **Changes:** Alembic revision for `question_variants` (D4, with `course_id`); one service
function `generate_computed_question` (so it can move to the job queue later); the program runs
through the configured executor (`graders/executors`, Piston in production, 64 KB output cap);
serving picks a copy by `attempt.id`; scoring uses that copy's key; review shows all K copies
side by side.
- **Accept:** (1) a program that crashes, prints invalid JSON, or produces copies that fail the
type's checks is repaired or rejected, never served; (2) two attempts can get different copies
and each is scored against its own key; (3) works on SQLite and Postgres (SQLAlchemy only);
(4) a student never receives the program or another copy's key.
- **Validate:** `pytest` (executor faked and real local), Alembic upgrade/downgrade, Chrome run of
a student answering two different copies.



### fig5 — Cross-subject eval (the universality proof)

- **Deliverable:** a measured report that figure questions work across dissimilar subjects.
- **Run:** for each of four courses (rule 6), draft figure styles from the course's own material
and generate about 10 questions per figure kind. Report per subject and kind: share with a valid
figure, share passing the judges, blind-solver agreement, computed-program success rate, and
professor accept rate on a small sample.
- **Accept:** every kind works in at least three of the four subjects, and no subject fails because
of wording that assumes another subject. Failures are filed as tasks with their evidence.
- **Validate:** **paid**, so ask first. Runs on a DB copy outside the repo
(`experiments-outside-repo` rule).



### fig6 — Professor controls

- **Deliverable:** a professor can edit a diagram or chart in review, regenerate one copy of a
computed question, and turn figures off for a course.
- **Changes:** the review edit path (`feedback/service.py:89`, today prompt/solution/tests only)
gains `figure`; the agent can revise a figure style in chat like any other style.
- **Accept:** an edit is stored as an edit (the original is kept, ADR-002), re-validated, and
re-judged.



## Risks

- **The LLM's generator programs fail often.** fig4 measures the pass rate before relying on it.
If it is low, computed styles stay opt-in.
- **Judges cannot see pictures.** D6 gives them `alt` and the program's data, but a misdrawn
diagram can still pass. A vision-model judge is the follow-up if fig5 shows this happening.
- **Mermaid layout.** Some diagram types lay out badly (seen with `stateDiagram`). The prompt rules
steer to flowcharts, and fig5 measures what is left.
- **Payload size.** Computed SVGs are 8–13 KB each. With K=3 that is up to about 40 KB per
question, outside `content_json` (D4).



## Not in these milestones

Figures from the course book (ingestion drops image blocks, `ingestion/parsing.py:241`; it needs
extraction and a vision model). Students drawing or clicking on a figure as their answer
(PrairieLearn's `pl-drawing`). Interactive HTML figures in questions. A vision-model judge.
Generating copies live, per student.