# Contributing a question style

A style is one reusable way of asking a question: one question type, a difficulty range, and two
worked examples a professor sees before approving it. Styles are YAML files, one per style:

```
styles/<subject>/<id>.yaml     # e.g. styles/intro_python/py.trace_steps.yaml
styles/<subject>/order.txt     # display order (optional; unlisted styles come last, by id)
styles/ids.lock                # every id ever shipped
styles/schema.json             # JSON Schema of a style file
```

## Add a style

1. Copy a style of the same question type in `styles/<subject>/` and rename the file. The file
   name is the id: `<prefix>.<snake_case_name>`, using the prefix every other style of that
   subject uses (`py` for `intro_python`). `id` and `subject` may be left out of the file; if
   present they must match the path.
2. Fill in the fields. `styles/schema.json` describes each one; an editor with YAML language
   support validates as you type if the file starts with
   `# yaml-language-server: $schema=../schema.json`.
3. Write exactly two examples. They must be real, correct questions:
   - `multiple_choice`: `options` with exactly one `correct: true`; `answer` explains it.
   - `true_false`: options `True` and `False`, one correct.
   - `output_prediction`: `code` and `answer` = exactly what the code prints.
   - `parsons`: `lines` in the correct order, indented with 4 spaces per level.
   - `code_completion`, `debugging`, `coding`: a `solution` (the correct program) and
     `test_cases`, each an `assert:` (and/or `stdin:` / `stdout:`), with `tests` equal to their
     count. For `debugging`, `code` must fail at least one test.
4. Append `<subject>/<id>` to `styles/ids.lock`.
5. Run the checks:

   ```
   .\.venv\Scripts\python.exe -m pytest tests/test_styles.py
   ```

   Each example goes through its question type's authoring checks and its grader, the same gates
   a generated question passes. A failure names the style, the example and the check.

## Never rename or remove an id

Questions and approved setups store style ids. Removing or renaming one fails CI
(`styles/ids.lock`). To change a style's meaning, add a new style with a new id. Wording,
examples and hints of an existing style may be edited freely.

## Changing the schema

`styles/schema.json` is generated from `QuestionStyle` (`app/styles/schema.py`). After changing
the model, run `.\.venv\Scripts\python.exe -m scripts.export_style_schema`; a test fails while the
file is stale.
