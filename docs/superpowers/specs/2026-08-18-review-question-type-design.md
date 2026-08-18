## Review question-type designs

**Date:** 2026-08-18  
**Status:** finalized for implementation

## Goal

Finalize the review-body design for all seven question types in the Next.js professor console.

This document settles only the **middle of the review screen**: the question-type-specific body.
The surrounding shell is already decided by the review-loop design:

- queue progress
- disagreement / outcome banners
- review form and action bar
- judge rail
- post-submit learning feedback

The shell stays fixed. The body switches on `question_type`.

## Decision

Build one shared `QuestionBody` renderer that switches on `question.question_type` and reads from
`QuestionDetail.content`, not from the flattened legacy columns.

The backend already returns the typed data needed for this:

- `options`
- `correct_option_index`
- `correct_answer`
- `code`
- `expected_output`
- `blocks`
- `correct_order`
- `reference_solution`
- `tests`
- `explanation`

No backend change is required for these designs.

## Why

The current generic projection is only truly native for `coding`.

For the other six types, the legacy columns are storage artifacts:

- `multiple_choice`: `reference_solution` is only the text of the correct option
- `true_false`: `reference_solution` is only `"true"` or `"false"`
- `output_prediction`: `reference_solution` is only the expected stdout
- `parsons`: `reference_solution` is serialized JSON, not the reconstructed program

Reviewing the flattened projection means reviewing the wrong shape.

## Shared rules

1. Show the student-facing surface first and the key second.
2. Attach deterministic failures to the field they invalidate, not only to a checks list below.
3. Always show `explanation`; it is student-facing content and is currently under-reviewed.
4. Preserve student order exactly when order is part of the question.
5. Use `content` as the display source; use legacy `prompt` / `reference_solution` / `tests` only
   for edit persistence and compatibility.

## Type designs

### `multiple_choice`

**Body**

- Prompt
- Full options list, in student order
- Correct option visually marked in review mode only
- Explanation panel below

**What review turns on**

- whether distractors are distinct and diagnostically useful
- whether two wrong options repeat the same mistake
- whether the correct option is obvious for the wrong reason

**Checks that anchor to this body**

- `mc_options_valid`
- `mc_no_duplicate_options`
- `mc_correct_option_exists`
- `mc_explanation_present`

**Rules**

- Never reorder options.
- Never extract only the correct option into a separate answer panel.
- Render code-like options in monospace.

### `true_false`

**Body**

- Prompt
- One compact answer band showing `True` / `False`, with the correct side marked in review mode
- Explanation panel as the main secondary content

**What review turns on**

- whether the explanation is substantive enough to justify a binary item
- whether the statement tests understanding rather than a coin flip

**Checks that anchor to this body**

- `tf_boolean_answer`
- `tf_explanation_present`

**Rules**

- Do not give the boolean answer its own large panel.
- Do not render the string `"true"` or `"false"` as if it were a code answer.

### `output_prediction`

**Body**

- Prompt
- Code panel
- Claimed output panel
- Observed output panel from deterministic execution
- Explanation panel

**What review turns on**

- usually nothing, when claimed and observed output differ: the interpreter has already ruled
- when they agree, whether the code example is pedagogically useful and fairly scoped

**Checks that anchor to this body**

- `output_code_parses`
- `expected_output_verified`

**Rules**

- Show both claimed output and observed output.
- When deterministic execution disagrees, surface that mismatch inline on the output field itself.
- Treat interpreter disagreement as a blocking defect, not a subtle warning.

### `code_completion`

**Body**

- Prompt
- Student stub on the left
- Full reference solution on the right
- Added region highlighted relative to the stub
- Tests table below
- Explanation panel

**What review turns on**

- whether the gap is the learning point
- whether the missing region is too trivial or too broad
- whether the stub and solution differ where the prompt implies they should

**Checks that anchor to this body**

- `completion_reference_parses`
- `harness_valid`
- `reference_passes_tests`

**Rules**

- Show the full reference, not only a diff.
- Use highlighting to expose what the solution adds, but keep the full solution readable and editable.
- Do not assume the gap marker convention is present in the source code.

### `debugging`

**Body**

- Prompt
- Broken code on the left
- Fixed reference on the right
- Evidence band directly under the pair showing what the broken code actually did under the tests
- Tests table below
- Explanation panel

**What review turns on**

- whether the bug is real
- whether the bug is plausible for the student level
- whether the fixed reference actually addresses the exhibited failure

**Checks that anchor to this body**

- `debug_broken_exhibits_issue`
- `debug_reference_parses`
- `harness_valid`
- `reference_passes_tests`

**Rules**

- Put the broken-run evidence directly below the code pair, not only in a checks summary.
- If the broken code passes everything, state that inline as a blocking defect.
- Highlight the changed region between broken and fixed code, but keep both whole programs visible.

### `parsons`

**Body**

- Prompt
- Shuffled blocks panel on the left, with indentation rendered as indentation
- Canonically assembled program on the right, reconstructed from `correct_order` and `indent`
- Explanation panel below

**What review turns on**

- whether the canonical order teaches a meaningful ordering skill
- whether the indentation contributes to the concept being taught
- whether the shuffled blocks form a fair puzzle

**Checks that anchor to this body**

- `parsons_order_consistent`
- `parsons_indent_valid`
- `parsons_reference_compiles`

**Rules**

- Never show block ids to the professor as the primary reading surface.
- Render `indent` as leading whitespace, not as an integer label.
- Show the reconstructed program rather than raw JSON.
- If reconstruction fails to compile, show the assembled source and the compile error inline.

### `coding`

**Body**

- Prompt
- Reference solution panel
- Tests table below
- Explanation panel

**What review turns on**

- whether the tests are sufficient
- whether the reference is idiomatic for the taught concept
- whether the prompt and tests leave room for wrong but passing answers

**Checks that anchor to this body**

- `coding_reference_parses`
- `harness_valid`
- `reference_passes_tests`

**Rules**

- This is the one type the current generic shape mostly fits.
- The improvement here is mainly the tests table and explanation placement, not a new body pattern.

## Tests table design

The executable types share one tests renderer:

- `code_completion`
- `debugging`
- `coding`

Render tests as a table, not a JSON blob.

**Columns**

- `stdin`
- `expects`
- `reference`

**Behavior**

- `expects` shows `stdout`, `assert`, or both, depending on the stored case
- `reference` shows whether the reference run passed that row
- keep a raw JSON editing path for mutation, because the backend still writes `tests` as text

The table is the read surface. Raw JSON is the write surface.

## Component shape

Implement one shared body component, not seven separate pages.

Suggested structure:

- `QuestionBody`
- `QuestionExplanation`
- `QuestionChecks`
- `ExecutableTestsTable`
- `QuestionKeyMode`

`QuestionBody` takes:

- `question`
- `content`
- `validationChecks`
- `mode`

Where `mode` is at least:

- `review`
- `student`

The same renderer should later be reused by training where possible, with the key hidden in
student mode. This keeps professor and student views aligned to the same underlying question
shape.

## Implementation order

1. `parsons`
2. `debugging`
3. `output_prediction`
4. `multiple_choice`
5. `true_false`
6. `code_completion`
7. `coding`

This order fixes the worst current misprojections first:

- raw JSON shown as an answer
- deterministic evidence currently discarded
- distractor review currently flattened away

## Non-goals

- changing review routing, verdict semantics, or outcome storage
- changing `ReviewRequest`
- changing generation schemas
- changing scoring rules
- changing deterministic validation logic

## Source alignment

This design is aligned to the current implementation in:

- `app/generation/schemas.py`
- `app/validation/type_checks.py`
- `app/adaptive/scoring.py`
- `app/web/routes/api/schemas.py`
- `frontend/src/app/review/page.tsx`

The frontend work that follows this doc is rendering work, not backend contract work.
