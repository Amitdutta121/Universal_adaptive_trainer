# Project Notes

## Data Contracts

This repository deliberately accepts only structured JSON inputs for imported books and curriculum.

- Books must already be represented as structured JSON with chapters, sections, text, and page metadata.
- Curriculum must already be represented as structured JSON with Topic -> Subtopic hierarchy.
- There is no PDF, EPUB, or HTML parser in this repository.

Sample documents:

- [book_document_example.json](book_document_example.json)
- [taxonomy_document_example.json](taxonomy_document_example.json)

The project chooses deterministic, auditable imports over heuristic document parsing.

## Current Constraints

- Imports are JSON-only by design.
- Coverage gap selection exists, but targeted generation for a named gap is intentionally not implemented because the generator classifies output after generation rather than being aimed at a subtopic directly.
- Local SQLite behavior matters in a few places because this repo is built and tested around local development first.

## More Reading

- [DECISIONS.md](DECISIONS.md)
- [ADAPTIVE_TUNING_README.md](ADAPTIVE_TUNING_README.md)
- [JUDGE_ALIGNMENT_EXPERIMENTS.md](JUDGE_ALIGNMENT_EXPERIMENTS.md)
- [frontend/README.md](../frontend/README.md)
