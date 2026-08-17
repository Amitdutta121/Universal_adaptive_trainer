"""Spike: topic -> retrieve section -> generate questions -> reject near-duplicates.

Standalone verification of the proposed agent, deliberately independent of
``app/``. Nothing here imports the application and nothing here is meant to
survive into it. The point is to find out whether the three moving parts work
at all before any of them is designed into a system.

What it verifies, in order:

1. **Retrieval** -- given a topic string, does ranking the book's sections
   surface the section that actually teaches it? Printed with full citations so
   the answer is checkable by eye rather than asserted.
2. **Generation** -- does a usable question come back from the retrieved
   section, in a parseable and complete form?
3. **Deduplication** -- generating N questions from *one* section is the
   adversarial case for duplicates, so the run is its own test. Every rejection
   is reported, and so is the highest similarity among the questions that were
   *accepted*, which is what says whether the threshold is doing any work.

Run the plumbing for free first, no API calls, canned questions containing a
deliberate near-duplicate::

    .\\.venv\\Scripts\\python.exe spikes\\topic_agent_spike.py --dry-run

Then against a real model::

    .\\.venv\\Scripts\\python.exe spikes\\topic_agent_spike.py --topic "list comprehensions" -n 8

Printing to stdout is this script's interface; the no-``print`` convention
applies to ``app/``, which this is not.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BOOK = PROJECT_ROOT / "docs" / "book_document_example.json"

#: Below this, a retrieved section is too thin to generate a real question from.
#: The bundled example book has one-sentence sections, so it exercises the
#: plumbing and nothing else.
THIN_SECTION_CHARS = 200

#: Generation attempts per question before giving up on finding a non-duplicate.
#: Mirrors the retry-with-the-defect-stated shape the application already uses.
MAX_ATTEMPTS = 3

_WORD = re.compile(r"[a-z0-9_]+")

_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "for", "from",
        "has", "have", "how", "if", "in", "into", "is", "it", "its", "may", "not", "of", "on",
        "or", "that", "the", "their", "then", "there", "these", "this", "to", "use", "used",
        "using", "was", "what", "when", "which", "will", "with", "you", "your",
    }
)  # fmt: skip


# --------------------------------------------------------------------------
# Environment
# --------------------------------------------------------------------------


def load_dotenv(path: Path) -> None:
    """Read ``KEY=value`` lines into ``os.environ`` without overriding real vars.

    Deliberately hand-rolled: this script must not depend on the application's
    settings object, or it stops being an independent check of the idea.
    """
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


# --------------------------------------------------------------------------
# Book
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Section:
    """One instructional section, flattened out of the book document."""

    book_title: str
    chapter_number: str
    chapter_title: str | None
    number: str | None
    title: str | None
    text: str
    start_page: int | None
    end_page: int | None

    def citation(self) -> str:
        """Book -> chapter -> section -> pages, degrading when labels are absent."""
        label = self.title or (f"section {self.number}" if self.number else "unlabelled section")
        chapter = self.chapter_title or f"chapter {self.chapter_number}"
        pages = ""
        if self.start_page is not None:
            pages = f", p.{self.start_page}"
            if self.end_page is not None and self.end_page != self.start_page:
                pages += f"-{self.end_page}"
        return f"{self.book_title} / {chapter} / {label}{pages}"


def load_sections(path: Path) -> list[Section]:
    """Flatten a structured book document into its sections.

    No parsing and no heading detection: the document declares its own
    structure, and this only walks what it declares.
    """
    document = json.loads(path.read_text(encoding="utf-8"))
    book_title = document.get("title") or path.stem
    sections: list[Section] = []
    for chapter in document.get("chapters", []):
        for section in chapter.get("sections", []):
            text = section.get("text") or ""
            if not text.strip():
                continue
            sections.append(
                Section(
                    book_title=book_title,
                    chapter_number=str(chapter.get("number", "?")),
                    chapter_title=chapter.get("title"),
                    number=section.get("number"),
                    title=section.get("title"),
                    text=text,
                    start_page=section.get("start_page"),
                    end_page=section.get("end_page"),
                )
            )
    return sections


# --------------------------------------------------------------------------
# Vectors
# --------------------------------------------------------------------------

Vector = dict[str, float]


def cosine(a: Vector, b: Vector) -> float:
    """Cosine similarity over sparse vectors. Both embedders emit this shape."""
    if not a or not b:
        return 0.0
    shared = a.keys() & b.keys()
    if not shared:
        return 0.0
    dot = sum(a[key] * b[key] for key in shared)
    norm_a = math.sqrt(sum(value * value for value in a.values()))
    norm_b = math.sqrt(sum(value * value for value in b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def tokenize(text: str) -> list[str]:
    return [word for word in _WORD.findall(text.lower()) if word not in _STOPWORDS]


class LexicalEmbedder:
    """TF-IDF over the book's own vocabulary. No API key, no cost, no network.

    Deliberately the default. It catches literal near-copies, which is the
    duplicate mode a generator looping on one section actually produces, and it
    lets the whole pipeline be verified before a cent is spent. It will miss a
    paraphrase; ``--embedder openai`` is there to show what that costs.
    """

    name = "lexical-tfidf"

    def __init__(self, corpus: list[str]) -> None:
        documents = [set(tokenize(text)) for text in corpus]
        total = len(documents) or 1
        frequencies: dict[str, int] = {}
        for document in documents:
            for term in document:
                frequencies[term] = frequencies.get(term, 0) + 1
        self._idf = {
            term: math.log((total + 1) / (count + 1)) + 1.0 for term, count in frequencies.items()
        }
        # An unseen term is maximally distinctive, not unknown-and-therefore-zero.
        self._default_idf = math.log(total + 1) + 1.0

    def encode(self, texts: list[str]) -> list[Vector]:
        vectors: list[Vector] = []
        for text in texts:
            counts: dict[str, float] = {}
            for term in tokenize(text):
                counts[term] = counts.get(term, 0.0) + 1.0
            vectors.append(
                {
                    term: count * self._idf.get(term, self._default_idf)
                    for term, count in counts.items()
                }
            )
        return vectors


class OpenAIEmbedder:
    """Dense embeddings, for comparison against the lexical default.

    Uses ``OPENAI_API_KEY`` and api.openai.com directly, *not* the OpenRouter
    credential. I have not verified that OpenRouter serves an embeddings
    endpoint at all -- the application's ``embedding_model`` setting currently
    has no consumer, so nothing has ever exercised it.
    """

    name = "openai-embeddings"

    def __init__(self, model: str) -> None:
        from openai import OpenAI

        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise SystemExit(
                "--embedder openai needs OPENAI_API_KEY (an OpenAI key, not the OpenRouter one)"
            )
        self._client = OpenAI(api_key=key)
        self._model = model

    def encode(self, texts: list[str]) -> list[Vector]:
        response = self._client.embeddings.create(model=self._model, input=texts)
        return [
            {str(index): value for index, value in enumerate(item.embedding)}
            for item in response.data
        ]


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------


@dataclass
class Question:
    """One generated question, plus how it got here."""

    prompt: str
    options: list[str]
    answer: str
    explanation: str
    attempts: int = 1
    rejected_against: list[tuple[int, float]] = field(default_factory=list)

    def dedup_text(self) -> str:
        """What the duplicate check compares.

        The stem alone is too narrow -- two questions can share a stem and test
        different things -- and the explanation is too broad, since it restates
        the section for every question and would inflate every pair.
        """
        return f"{self.prompt}\n" + "\n".join(self.options)


SYSTEM = (
    "You write multiple-choice Python assessment questions from a passage of a textbook. "
    "Use only what the passage supports. Return strict JSON with keys: prompt (string), "
    "options (array of exactly 4 strings), answer (one of the options, verbatim), "
    "explanation (string). No markdown, no commentary, no code fences."
)


def _extract_json(content: str) -> dict[str, object]:
    """Parse the model's reply, tolerating fences it was told not to emit."""
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object in reply: {content[:200]!r}")
    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("reply was not a JSON object")
    return parsed


def _to_question(payload: dict[str, object]) -> Question:
    prompt = str(payload.get("prompt", "")).strip()
    options = [str(option).strip() for option in payload.get("options", []) or []]
    answer = str(payload.get("answer", "")).strip()
    explanation = str(payload.get("explanation", "")).strip()
    if not prompt:
        raise ValueError("empty prompt")
    if len(options) != 4:
        raise ValueError(f"expected 4 options, got {len(options)}")
    if answer not in options:
        raise ValueError("answer is not one of the options")
    return Question(prompt=prompt, options=options, answer=answer, explanation=explanation)


class Generator:
    """One chat call per attempt, against whatever OpenRouter route is configured."""

    def __init__(self, model: str, temperature: float) -> None:
        from openai import OpenAI

        key = os.environ.get("LLM_API_KEY")
        if not key:
            raise SystemExit("LLM_API_KEY is not set (add it to .env or use --dry-run)")
        base_url = os.environ.get("LLM_BASE_URL") or "https://openrouter.ai/api/v1"
        self._client = OpenAI(api_key=key, base_url=base_url)
        self._model = model
        self._temperature = temperature
        self.calls = 0

    def generate(self, section: Section, topic: str, avoid: str | None) -> Question:
        instruction = (
            f"Topic the professor asked for: {topic}\n\n"
            f"Passage ({section.citation()}):\n{section.text}\n\n"
            "Write ONE multiple-choice question."
        )
        if avoid:
            instruction += (
                "\n\nYour previous attempt was rejected as a near-duplicate of a question "
                f"already accepted:\n{avoid}\n\n"
                "Write a question that tests a DIFFERENT aspect of the passage. Do not "
                "reword the rejected one."
            )
        self.calls += 1
        response = self._client.chat.completions.create(
            model=self._model,
            temperature=self._temperature,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": instruction},
            ],
        )
        return _to_question(_extract_json(response.choices[0].message.content or ""))


CANNED = [
    Question(
        prompt="What does a list comprehension produce?",
        options=["A new list", "A generator", "A tuple", "A dictionary"],
        answer="A new list",
        explanation="It builds and returns a new list.",
    ),
    # Deliberate near-duplicate of the first: the dedup check must catch this.
    Question(
        prompt="What does a list comprehension produce as its result?",
        options=["A new list", "A generator", "A set", "A dictionary"],
        answer="A new list",
        explanation="It builds and returns a new list.",
    ),
    Question(
        prompt="Which clause filters elements inside a list comprehension?",
        options=["if", "while", "with", "assert"],
        answer="if",
        explanation="A trailing if clause filters.",
    ),
    Question(
        prompt="A program is best described as which of the following?",
        options=[
            "A sequence of instructions",
            "A single variable",
            "A page of a book",
            "A hardware device",
        ],
        answer="A sequence of instructions",
        explanation="A program specifies how to perform a computation.",
    ),
]


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------


@dataclass
class Rejection:
    index: int
    attempt: int
    duplicate_of: int
    similarity: float
    prompt: str


def run(args: argparse.Namespace) -> int:
    sections = load_sections(Path(args.book))
    if not sections:
        raise SystemExit(f"no sections with text in {args.book}")

    embedder: LexicalEmbedder | OpenAIEmbedder
    if args.embedder == "openai":
        embedder = OpenAIEmbedder(args.embedding_model)
    else:
        embedder = LexicalEmbedder([section.text for section in sections])

    # -- 1. retrieval ------------------------------------------------------
    topic = args.topic or "list comprehensions"
    section_vectors = embedder.encode([f"{s.title or ''}\n{s.text}" for s in sections])
    topic_vector = embedder.encode([topic])[0]
    scored = zip(section_vectors, sections, strict=True)
    ranked = sorted(
        ((cosine(topic_vector, vector), section) for vector, section in scored),
        key=lambda pair: pair[0],
        reverse=True,
    )

    print("=" * 78)
    print(f"RETRIEVAL   topic={topic!r}   embedder={embedder.name}   sections={len(sections)}")
    print("=" * 78)
    for rank, (score, section) in enumerate(ranked[: args.top_k], start=1):
        marker = "->" if rank == 1 else "  "
        print(f"{marker} {rank}. {score:.3f}  {section.citation()}")
        print(f"      {section.text[:110].strip()}...")
    chosen_score, chosen = ranked[0]
    if chosen_score <= 0.0:
        print("\n  WARNING: top section scored 0.0 -- no term overlap with the topic at all.")
    if len(chosen.text) < THIN_SECTION_CHARS:
        print(
            f"\n  WARNING: chosen section is {len(chosen.text)} chars. The bundled example book"
            "\n  has one-sentence sections; point --book at a real document to judge quality."
        )

    # -- 2 + 3. generation with the duplicate gate -------------------------
    accepted: list[Question] = []
    accepted_vectors: list[Vector] = []
    rejections: list[Rejection] = []
    generator = None if args.dry_run else Generator(args.model, args.temperature)

    print()
    print("=" * 78)
    print(f"GENERATION + DEDUP   n={args.questions}   threshold={args.threshold:.2f}")
    print("=" * 78)

    for index in range(1, args.questions + 1):
        avoid: str | None = None
        placed = False
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if args.dry_run:
                candidate = CANNED[(index - 1 + attempt - 1) % len(CANNED)]
                candidate = Question(
                    prompt=candidate.prompt,
                    options=list(candidate.options),
                    answer=candidate.answer,
                    explanation=candidate.explanation,
                )
            else:
                assert generator is not None
                try:
                    candidate = generator.generate(chosen, topic, avoid)
                except (ValueError, json.JSONDecodeError) as error:
                    print(f"  {index}. attempt {attempt}: unusable reply -- {error}")
                    continue

            vector = embedder.encode([candidate.dedup_text()])[0]
            scores = [cosine(vector, existing) for existing in accepted_vectors]
            worst = max(scores) if scores else 0.0
            worst_index = scores.index(worst) + 1 if scores else 0

            if worst >= args.threshold:
                rejections.append(Rejection(index, attempt, worst_index, worst, candidate.prompt))
                print(
                    f"  {index}. attempt {attempt}: REJECTED as duplicate of #{worst_index} "
                    f"(sim {worst:.3f})  {candidate.prompt[:60]!r}"
                )
                avoid = accepted[worst_index - 1].dedup_text()
                continue

            candidate.attempts = attempt
            accepted.append(candidate)
            accepted_vectors.append(vector)
            print(
                f"  {index}. accepted on attempt {attempt} "
                f"(max sim to bank {worst:.3f})  {candidate.prompt[:60]!r}"
            )
            placed = True
            break

        if not placed:
            print(f"  {index}. GAVE UP after {MAX_ATTEMPTS} attempts -- every one was a duplicate")

    # -- report ------------------------------------------------------------
    pairs = [
        (i + 1, j + 1, cosine(accepted_vectors[i], accepted_vectors[j]))
        for i in range(len(accepted_vectors))
        for j in range(i + 1, len(accepted_vectors))
    ]
    highest = max(pairs, key=lambda triple: triple[2]) if pairs else None

    print()
    print("=" * 78)
    print("RESULT")
    print("=" * 78)
    print(f"  requested          {args.questions}")
    print(f"  accepted           {len(accepted)}")
    print(f"  duplicate rejects  {len(rejections)}")
    if generator is not None:
        print(f"  model calls        {generator.calls}")
    print(f"  threshold          {args.threshold:.2f}")
    if highest:
        print(
            f"  highest similarity among ACCEPTED: {highest[2]:.3f} "
            f"(#{highest[0]} vs #{highest[1]})"
        )
        print(f"    headroom to threshold: {args.threshold - highest[2]:+.3f}")
    if rejections:
        lowest_reject = min(rejection.similarity for rejection in rejections)
        print(f"  lowest similarity that was REJECTED: {lowest_reject:.3f}")
        if highest and lowest_reject - highest[2] < 0.05:
            print("    NOTE: accepted and rejected populations nearly touch. The threshold is")
            print("    sitting inside the noise; calibrate it before trusting either side.")

    print()
    print("  Verdict:")
    print(
        f"    retrieval  {'OK' if chosen_score > 0 else 'FAILED -- no overlap'}"
        f"  (top hit {chosen_score:.3f}: {chosen.citation()})"
    )
    print(f"    generation {'OK' if accepted else 'FAILED -- nothing accepted'}")
    if rejections:
        print(f"    dedup      FIRED {len(rejections)}x -- the gate demonstrably rejects")
    elif highest is not None:
        print("    dedup      NEVER FIRED. Either the generator is genuinely diverse or the")
        print(f"               threshold is too high -- highest pair was {highest[2]:.3f}.")
    else:
        print("    dedup      not exercised (fewer than 2 accepted)")

    if args.show:
        print()
        for number, question in enumerate(accepted, start=1):
            print(f"--- #{number} (attempt {question.attempts}) ---")
            print(f"  {question.prompt}")
            for option in question.options:
                mark = "*" if option == question.answer else " "
                print(f"   {mark} {option}")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--topic", help="Python topic to retrieve and generate from")
    parser.add_argument("--book", default=str(DEFAULT_BOOK), help="structured book JSON")
    parser.add_argument("-n", "--questions", type=int, default=6)
    parser.add_argument("--threshold", type=float, default=0.80, help="duplicate cutoff (cosine)")
    parser.add_argument("--top-k", type=int, default=5, help="retrieval hits to print")
    parser.add_argument("--embedder", choices=["lexical", "openai"], default="lexical")
    parser.add_argument("--embedding-model", default="text-embedding-3-small")
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL", "deepseek/deepseek-chat"))
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--dry-run", action="store_true", help="no API calls; canned questions")
    parser.add_argument("--show", action="store_true", help="print the accepted questions")
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
