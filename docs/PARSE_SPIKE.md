# Parse spike: Docling vs unstructured (Task 3)

**Decision (Checkpoint A, 2026-10-14): Docling.**

**Recommendation: Docling** (`DocumentConverter` + `HybridChunker`, OCR off for born-digital PDFs), in an
optional dependency group, run inside the existing background import job. For PDFs, keep building the
heading path from the PDF's own outline (PyMuPDF `get_toc()`, which we already use) and attach it to
each Docling chunk by page and heading text. Docling's own heading levels are flat (see below).

Run on 2026-10-14 against `Introduction_to_Data_Science_Using_Python_Agah.pdf` (117 pages, born-digital,
has an embedded outline), Windows 11, CPU only. Scripts and raw outputs are in `spikes/parse_spike/`
(not committed; `run_docling.py`, `run_unstructured.py`, `compare.py`, `office_check.py`).

## Comparison

| | Docling 2.x | unstructured `fast` | unstructured `hi_res` |
|---|---|---|---|
| Time, whole book | 69 s warm (92 s first run) | **8 s** | 281 s |
| Chunks (median / max chars) | 174 (677 / 1204) | 247 (285 / 1485) | 154 (585 / 1496) |
| Pages covered | 117/117 | 117/117 | 117/117 |
| Pages the current import loses (15) | 15/15 | 15/15 | 15/15 |
| Gold queries with an overlapping chunk | 66/66 | 66/66 | 66/66 |
| TOC headings detected | **66/66** | 33/66 (1,108 "Title" elements, mostly code lines) | **66/66** |
| Heading levels | flat (all level 1) | none | none |
| Heading path on 3 known sections | last heading only, 3/3 correct | 1/3 correct | last heading only, 3/3 correct |
| Tables | **11, with header rows** (Table 2-1, 3-1, ASCII, colours) | 0 (no table detection) | 11, header rows often lost, OCR errors (`0`→`O`, `00h`→`OOh`) |
| Code | 97 chunks contain fenced `code` blocks; line breaks inside a block sometimes collapse | plain text, newlines kept, not labelled | plain text, not labelled |
| System dependencies | none | none | **Tesseract + Poppler binaries** (plus `TESSDATA_PREFIX`) |
| Install size | venv 1.2 GB (CPU torch) + 507 MB models | venv 711 MB | venv 711 MB + ~206 MB models + Tesseract |
| License | MIT | Apache-2.0 | Apache-2.0 |

Neither library keeps Python indentation reliably (the PDF lays code out with tab stops). That's fine
for retrieval. It means executable content must come from tools (`python_trace`, Task 20), never from
parsed code, as the plan already says.

### DOCX / PPTX (tested on a generated 2-heading DOCX with a table, and a 2-slide PPTX)

| | Docling | unstructured |
|---|---|---|
| DOCX | Real heading path (`['5. Functions', '5.1. Void and …']`); table rows kept; **no page numbers** (DOCX has none) | `category_depth` 0/1 on titles, but chunks carry no heading path; table kept; no page numbers |
| PPTX | One chunk per slide, slide number as `page`, slide title as heading | `chunk_by_title` merged both slides into one chunk; slide body classified as `Title` |
| Notes | Same `DocumentConverter` call for every format | `partition.auto` **segfaulted** on Windows (file-type sniffing); `partition_docx`/`partition_pptx` work |

DOCX has no pages, so the chunk model can't assume one: page range should be nullable, and heading
path plus position must be enough to locate a chunk. Task 4 must allow for this.

## Three sample chunks per library

**Docling**
1. `['4.4. Nested Loops']`, p33: "A nested loop means a loop inside another loop, and these are typically used for working
   with two dimensions. When a loop is nested inside another loop, the inner loop runs many times inside the
   outer loop. The inner loop will be restarted in each iteration of the outer loop…"
2. `['11.2 Inheritance']`, p66–67: "Inheritance allows one class to inherit attributes and methods from another.
   Parent class or base class is the class being inherited from, and child class is the class that is
   inherited from a parent class…" (note: the page-number footer "66" was dropped mid-sentence)
3. `['15.2 T-Test']`, p87: "Many times, in statistics, we need to compare several samples to conclude the given
   data. A t-test is used to see if there is a significant difference between two groups of data…"

**unstructured `hi_res`**
1. `['4.4. Nested Loops']`, p33: "4.4. Nested Loops A nested loop means a loop inside another loop… the inner loop
   will be re- started in each iteration…" (hyphenation artefact kept)
2. `['11.2 Inheritance']`, p66–67: "11.2 Inheritance Inheritance allows one class to inherit… child class is the
   66 class that is inherited from a parent class…" (page footer "66" left inside the sentence)
3. `['15.2 T-Test']`, p87: "15.2 T-Test Many times, in statistics, we need to compare several samples…"

**unstructured `fast`** (for contrast): the Nested Loops chunk is headed `'Go to 4.3 Practice Question
Solutions.'` and starts on p32, and the T-Test text sits in a chunk headed `'print(old)'`. Code lines
get detected as titles.

## Heading-path check against the table of contents (manual)

| Section | TOC path | Docling | unstructured `hi_res` | unstructured `fast` |
|---|---|---|---|---|
| 4.4 Nested Loops (p33) | 4. Repetitions › 4.4. Nested Loops | 4.4. Nested Loops ✔ (leaf) | 4.4. Nested Loops ✔ (leaf) | ✘ |
| 11.2 Inheritance (p66) | 11. Object Oriented Programming › 11.2 Inheritance | ✔ (leaf) | ✔ (leaf) | ✔ (leaf) |
| 15.2 T-Test (p87) | 15. Python and Statistics › 15.2 T-Test | ✔ (leaf) | ✔ (leaf) | ✘ |

No library returns the chapter level for a PDF. For an outlined PDF, the full path comes from the
embedded TOC, which matched all 66 entries.

## Why Docling

- It's the only option that gets tables right without system binaries, and the book's tables (truth
  tables, operator tables, the `ord`/`chr` table) are question material.
- It labels code blocks, so chunks can mark code-bearing text for the tutorial recipes.
- One API for PDF, DOCX and PPTX, with real heading levels for DOCX and per-slide chunks for PPTX.
- It needs no Tesseract or Poppler, so the later Postgres/container deploy stays a pip install.

**Costs to accept:** ~1.7 GB installed (CPU torch + models), and about 0.6 s per page on CPU. Mitigate
with an optional dependency group, models cached on first run (`HF_HOME`), and the existing background
import job, which keeps the professor out of the wait.

**Main alternative:** unstructured `fast`, if install size or speed matters more than tables. It's 8×
faster and 1 GB lighter, but has no tables and half the headings wrong. `hi_res` is the worst of both:
4× slower than Docling, needs system binaries, and its tables are noisier.

## Retrieval, measured

Each parser's chunks are scored on the gold set with the baseline's embedder
(`text-embedding-3-small`), dense cosine and metrics (`spikes/parse_spike/eval_chunks.py`). "PyMuPDF"
is the no-new-dependency option: PyMuPDF (already in the app) page text, with the heading from the
PDF outline. Chunks are embedded with their heading path prepended, which beat raw text for every
parser except unstructured `fast`.

| chunks from | n | MRR@10 | R@5 | R@10 | student MRR@5 |
|---|---|---|---|---|---|
| *baseline: current sections* | 54 | 0.741 | 0.798 | 0.828 | 0.571 |
| PyMuPDF, 1 chunk per page | 117 | 0.855 | 0.908 | 0.952 | 0.750 |
| PyMuPDF, ~700-char chunks | 224 | 0.867 | 0.917 | 0.963 | 0.685 |
| unstructured `fast` | 247 | 0.862 | 0.893 | 0.956 | 0.835 |
| unstructured `hi_res` | 154 | 0.916 | 0.931 | 0.978 | 0.794 |
| **Docling HybridChunker** | 174 | **0.935** | **0.955** | **0.985** | **0.852** |

Paired bootstrap on MRR@10 (10,000 resamples of the 66 queries):

- Docling vs PyMuPDF per page: **+0.080**, 95% CI [+0.015, +0.150]. Docling better on 12 queries, worse on 5.
- Docling vs PyMuPDF ~700 chars: **+0.068**, 95% CI [+0.018, +0.125]. Better on 10, worse on 2.
- Docling vs unstructured `hi_res`: +0.019, 95% CI [−0.046, +0.085]. No measurable difference.

So:

- **Most of the gain is chunking every page.** Even plain PyMuPDF lifts MRR@10 from 0.741 to 0.855,
  with no new dependency.
- **Docling adds a further, real but modest +0.07–0.08 MRR**, mostly on student-style questions
  (0.852 vs 0.750). Its layout-aware chunks keep explanation and code together.
- `hi_res` retrieves as well as Docling but loses on cost: 4× slower and needs Tesseract and Poppler.
- nDCG isn't comparable across chunk sizes (finer chunks make more units relevant, which raises the
  ideal DCG), so it's left out here. Recall@k slightly favours chunks that span more pages.
- Caveats: one book, 66 queries, and a gold set written by the same person who ran the spike.

**Open for Checkpoint A:** the HybridChunker tokenizer warns past 512 tokens (default
`all-MiniLM-L6-v2`). Pass a tokenizer that matches the embedding model, or set `max_tokens`, in Task 5.
