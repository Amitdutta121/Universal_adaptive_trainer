"""Stage A: what one instructional section actually teaches.

This stage reads a section and names the assessable skills it introduces. It is
explicitly *not* term extraction. Pulling out the nouns of a textbook section
produces a glossary, and a glossary makes a useless knowledge-component model:
"variable", "value" and "assignment statement" are three entries a student cannot
practise separately and a weakness score cannot meaningfully distinguish.

The granularity rule, which the prompt states and the schema enforces
    A proposed concept must be something a professor could set several different
    questions on, a student could practise, and the adaptive engine could track a
    weakness for. Too fine and weakness never accumulates enough evidence to
    steer selection; too coarse and a weakness score stops pointing anywhere
    useful. :data:`~app.curriculum.schema.MAX_CONCEPTS_PER_SECTION` is the hard
    ceiling behind the instruction.

One call per section, deliberately
    Sections are the unit of the source model (ADR-015), and analysing them
    independently keeps each answer grounded in text the professor can open and
    check. Long sections are truncated for the model's context window only; the
    stored section is never altered, and truncation is reported on the proposal.
"""

from __future__ import annotations

import logging

from app.config import Settings, get_settings
from app.curriculum.schema import (
    MAX_CONCEPTS_PER_SECTION,
    SectionAnalysis,
    json_schema_for,
    parse_structured,
)
from app.domain.books import BookSection, SectionSource
from app.llm import StructuredLLMClient

logger = logging.getLogger(__name__)

SCHEMA_NAME = "record_section_analysis"
SCHEMA_DESCRIPTION = (
    "Record what one textbook section teaches, and the assessable concepts it introduces."
)

SYSTEM_PROMPT = """\
You are helping build a knowledge-component model for an introductory Python \
course. You are given one section of a textbook. Identify the instructional \
skills it teaches.

You are NOT extracting terminology. Do not propose a concept merely because a \
word appears in the text. Propose a concept only when the section actually \
teaches something a student could be asked to do.

A concept qualifies only if ALL of these hold:
  * a student can practise it;
  * it can be assessed with a Python exercise;
  * several genuinely different questions could be written about it;
  * a student's weakness in it would be worth tracking separately.

Reject concepts that are too small. "The len function", "the colon character" \
and "the word True" are not concepts; they are details of larger skills.

Reject concepts that are too large. "Python", "Programming" and "Data" are not \
concepts; a weakness score against them would point nowhere.

Good examples of the right size: "String indexing", "While loops", "Function \
parameters and arguments", "List slicing", "Dictionary lookup", "Catching \
exceptions".

Sections that teach nothing assessable - prefaces, acknowledgements, \
installation instructions, exercise lists, glossaries, indexes - must be marked \
is_instructional=false and must propose no concepts.

For each concept:
  * label: how THIS book names the skill. Use the book's own wording, not a \
standardised one; a later stage reconciles wordings across books.
  * topic_label: the broader area the skill belongs to, e.g. "Strings", \
"Loops", "Functions".
  * definition: what a student who has mastered it can do, in one or two \
sentences.
  * evidence: one to four short excerpts or examples taken from this section \
that show the skill being taught. Quote the section; do not invent examples.
  * confidence: how sure you are that this is a real, assessable concept taught \
here.

Propose at most {max_concepts} concepts for a section. If a section seems to \
teach more than that, it is being read too finely: merge the smallest ones into \
the skills they belong to.
"""


class SectionConceptExtractor:
    """Runs Stage A over individual sections."""

    def __init__(self, client: StructuredLLMClient, settings: Settings | None = None) -> None:
        self._client = client
        self._settings = settings or get_settings()

    def analyse(self, section: BookSection, source: SectionSource) -> tuple[SectionAnalysis, bool]:
        """Analyse one section.

        Returns:
            The analysis, and whether the section's text had to be truncated to
            fit the context budget. Truncation is returned rather than logged
            because the proposal must be able to declare it.

        Raises:
            LLMRequestError: the provider could not be reached.
            MalformedModelOutputError: the response did not satisfy the schema.
        """
        text, truncated = self._fit_to_budget(section.text)
        payload = self._client.complete_structured(
            system=SYSTEM_PROMPT.format(max_concepts=MAX_CONCEPTS_PER_SECTION),
            prompt=_build_prompt(section, source, text, truncated),
            schema_name=SCHEMA_NAME,
            schema_description=SCHEMA_DESCRIPTION,
            json_schema=json_schema_for(SectionAnalysis),
        )
        analysis = parse_structured(SectionAnalysis, payload, stage="section analysis")
        logger.debug(
            "Analysed section %s: instructional=%s, %d concept(s)",
            source.section_id,
            analysis.is_instructional,
            len(analysis.concepts),
        )
        return analysis, truncated

    def _fit_to_budget(self, text: str) -> tuple[str, bool]:
        """Trim section text to the context budget, reporting whether it was cut.

        Chunking for a model context window is allowed and is never persisted
        (ADR-015): the stored section stays whole, and only what is *sent* is
        shortened.
        """
        budget = self._settings.curriculum_section_char_budget
        if len(text) <= budget:
            return text, False
        return text[:budget], True


def _build_prompt(section: BookSection, source: SectionSource, text: str, truncated: bool) -> str:
    """Give the model the section, plus enough context to place it in its book."""
    heading = source.section_label or section.display_title()
    lines = [
        f"Book: {source.book_title}",
        f"Chapter: {source.chapter_label or 'not stated by the source'}",
        f"Section: {heading}",
    ]
    if source.location_label:
        lines.append(f"Location: {source.location_label}")
    if not section.has_detected_heading:
        # The source printed no heading here, so the model must not read one into
        # the label the UI shows for this section.
        lines.append("Note: this section has no heading in the source.")
    if truncated:
        lines.append("Note: the section text below was truncated to fit the context window.")
    lines.append("")
    lines.append("Section text:")
    lines.append(text)
    return "\n".join(lines)
