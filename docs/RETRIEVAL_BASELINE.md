# Retrieval baseline

The number later retrieval changes (chunks, Task 5–6; hybrid BM25 + RRF, Task 11) must not fall below.

**Retriever:** `SectionRetriever`, dense cosine over `section_embeddings` (`openai/text-embedding-3-small`),
one book in scope.
**Corpus:** Agah, *Introduction to Data Science Using Python* (117 pages), as imported by
`pymupdf-outline-extractor 1.0`: 54 sections. Book 4 in the dev database copied on 2026-10-14.
**Gold set:** `tests/fixtures/retrieval_gold.json`, 66 queries (36 headings, 12 curriculum subtopic
names, 18 student-style questions), built by `scripts/build_retrieval_gold.py`.
**Scoring:** page overlap, no LLM judge (`app/retrieval/eval.py`). A retrieved section is a hit when its
pages overlap the query's `relevant_pages`.

```
python -m scripts.eval_retrieval --db data/adaptive_trainer.db
```

## Results (2026-10-14)

| k | recall | precision | nDCG | MRR |
|---|---|---|---|---|
| 1 | 0.574 | 0.667 | 0.667 | 0.667 |
| 3 | 0.753 | 0.404 | 0.738 | 0.730 |
| 5 | 0.798 | 0.279 | 0.762 | 0.737 |
| 10 | 0.828 | 0.145 | 0.775 | 0.741 |

At k = 5, by query kind:

| kind | recall | precision | nDCG | MRR |
|---|---|---|---|---|
| heading (n=36) | 0.861 | 0.306 | 0.841 | 0.815 |
| student (n=18) | 0.722 | 0.222 | 0.613 | 0.571 |
| subtopic (n=12) | 0.722 | 0.283 | 0.747 | 0.750 |

## Reading it

- **Ceiling from the import, not the ranker.** 9 of 66 queries can't be answered by any section,
  because the import puts no section on chapter-intro pages: 10, 22, 37, 45, 50–54 (all of
  Lists), 56 (all of Arrays), 65, 71, 77, 84–85. So MRR and nDCG can't go above 57/66 = 0.864,
  and MRR@10 = 0.741 is 0.12 below that. Chunking every page (Task 5) should lift this ceiling
  before any ranking change does.
- **Duplicated sections.** Headings that share a page get the whole page as their text, so
  2.1.2/2.2, 7.1/7.2, 7.2.1/7.2.2, 11.1/11.2 and 14.1/14.1.2/14.1.3 are identical pairs or triples.
  They take two or three top-k slots with the same text. This raises precision@k a little and
  lowers recall for the same k.
- **Precision@k is capped by how few units are relevant.** Most queries have one to three
  relevant sections, so precision@10 ≤ 0.3 even for a perfect ranker. Compare it between runs,
  not against 1.0.
- **Student questions are the weak spot** (MRR@5 0.571 vs 0.815 for headings). That's where
  BM25 on code tokens (`randint`, `rstrip`, `ord(`) should help (Task 11).
- Query embeddings come from a hosted API, so a re-run can move the third decimal place.
  Count a change as real only when it's bigger than that.

## Chunks (Task 6, 2026-10-14)

`ChunkRetriever`, dense cosine over `chunk_embeddings` (same embedder), Agah re-imported with Docling:
174 chunks covering all 117 pages. Chunks are embedded with their heading path prepended.

```
python -m scripts.eval_retrieval            # --units chunks is the default
```

| k | recall | precision | nDCG | MRR |
|---|---|---|---|---|
| 1 | 0.632 | 0.894 | 0.894 | 0.894 |
| 3 | 0.888 | 0.662 | 0.779 | 0.924 |
| 5 | 0.954 | 0.512 | 0.786 | 0.932 |
| 10 | 0.989 | 0.305 | 0.821 | 0.934 |

At k = 5, by query kind:

| kind | recall | precision | nDCG | MRR |
|---|---|---|---|---|
| heading (n=36) | 0.971 | 0.561 | 0.836 | 0.951 |
| student (n=18) | 0.944 | 0.389 | 0.707 | 0.875 |
| subtopic (n=12) | 0.917 | 0.550 | 0.756 | 0.958 |

- **No regression; better on every metric at every k.** MRR@10 0.741 → 0.934, recall@10
  0.828 → 0.989, student MRR@5 0.571 → 0.875. It matches the parse spike's Docling number
  (0.935), so the in-app pipeline reproduces what the spike measured.
- **The import ceiling is gone:** 0 of 66 queries now have no overlapping unit (was 9).
- nDCG is not strictly comparable across unit sizes (see the parse spike); it rose anyway.

## Hybrid BM25 + RRF (Task 11, 2026-10-14)

`ChunkRetriever(hybrid=True)`: the dense cosine ranking and a `bm25s` ranking over the same
text (heading path + chunk text, English stopwords) merged by reciprocal rank fusion, k = 60,
equal weights. Same book, chunks and embedder as above; dense re-run in the same session.

```
python -m scripts.eval_retrieval --mode hybrid
```

| k | recall | precision | nDCG | MRR | Δ MRR vs dense |
|---|---|---|---|---|---|
| 1 | 0.564 | 0.818 | 0.818 | 0.818 | −0.076 |
| 3 | 0.872 | 0.626 | 0.732 | 0.881 | −0.043 |
| 5 | 0.937 | 0.476 | 0.734 | 0.885 | −0.047 |
| 10 | 0.965 | 0.291 | 0.777 | 0.888 | −0.046 |

At k = 5, by query kind:

| kind | recall | precision | nDCG | MRR |
|---|---|---|---|---|
| heading (n=36) | 0.977 | 0.556 | 0.823 | 0.926 |
| student (n=18) | 0.861 | 0.300 | 0.564 | 0.769 |
| subtopic (n=12) | 0.931 | 0.500 | 0.723 | 0.938 |

**Hybrid fails the acceptance bar: it is below dense on every metric at every k** (only
heading/subtopic recall@5 rise, by one query). The drop is largest where BM25 was supposed to
help: student MRR@5 0.875 → 0.769.

Why, from a one-off diagnostic (one embedding pass, same queries; not a committed script):

| variant | MRR@10 | nDCG@10 | R@5 | student MRR@5 | heading MRR@5 |
|---|---|---|---|---|---|
| dense | 0.934 | 0.824 | 0.954 | 0.875 | 0.951 |
| BM25 alone (heading + text) | 0.784 | 0.677 | 0.845 | 0.602 | 0.845 |
| BM25 alone (text only) | 0.666 | 0.557 | 0.781 | 0.622 | 0.630 |
| RRF k=60, 1:1 (shipped) | 0.888 | 0.778 | 0.937 | 0.769 | 0.926 |
| RRF k=60, dense 3:1 | 0.929 | 0.810 | 0.973 | 0.889 | 0.940 |
| RRF k=10, dense 2:1 | 0.929 | 0.820 | 0.977 | 0.917 | 0.926 |

- **BM25 is the weak leg, not the fusion.** Alone it is 0.15 MRR@10 below dense, and below it
  on student questions too. On a 174-chunk book whose chunks are already embedded with their
  heading path, the dense ranking has little left for exact-term matching to fix.
- **Down-weighting BM25 recovers dense but does not beat it** on MRR or nDCG; it gains a
  little recall@5. Those weights were picked on the gold set itself (66 queries), so the gains
  are within what tuning on the test set buys. Not adopted.
- **LlamaIndex `QueryFusionRetriever` was not tried.** Its `reciprocal_rerank` mode is the same
  formula, and its BM25 retriever is built on `bm25s`; it would reproduce this result.
- **Dense stays the default.** `hybrid` is off everywhere in the app; only
  `scripts/eval_retrieval.py --mode hybrid` turns it on. Worth re-running when a larger or
  more code-heavy book is in the gold set.
