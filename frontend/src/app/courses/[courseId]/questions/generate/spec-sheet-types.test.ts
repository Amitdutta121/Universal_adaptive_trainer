/**
 * What the sheet sends, and what it leaves out.
 *
 * `toRequestChunks` is the one place the console shapes a run, so the rules it
 * does encode — inherit the sheet default, skip untouched rows, skip chunks with
 * no text — are pinned here. Everything about how those counts become questions
 * belongs to the API and is tested there (`tests/test_generation_batch.py`).
 */

import { describe, expect, it } from "vitest";
import {
  type ChunkSpec,
  effectiveFormats,
  type SheetRow,
  specPerFormatTotal,
  specTotal,
  toRequestChunks,
} from "./spec-sheet-types";

const DEFAULTS = ["multiple_choice"] as const;

function row(sectionId: number, overrides: Partial<SheetRow> = {}): SheetRow {
  return {
    sectionId,
    bookId: 1,
    bookTitle: "Think Python",
    chapterId: 10,
    chapterLabel: "Chapter 4",
    title: `Section ${sectionId}`,
    locationLabel: "pp. 88-91",
    charCount: 3104,
    startPage: 88,
    endPage: 91,
    existingQuestionCount: 0,
    selectable: true,
    isUnlabelled: false,
    ...overrides,
  };
}

function spec(overrides: Partial<ChunkSpec> = {}): ChunkSpec {
  return { easy: 0, medium: 0, hard: 0, formats: null, ...overrides };
}

describe("specPerFormatTotal", () => {
  it("sums the three difficulties, before formats are applied", () => {
    expect(specPerFormatTotal(spec({ easy: 1, medium: 2, hard: 3 }))).toBe(6);
  });
});

describe("specTotal", () => {
  it("makes every count in every chosen format", () => {
    // One of each difficulty, two formats: MCQ and Parsons at all three levels.
    expect(
      specTotal(
        spec({ easy: 1, medium: 1, hard: 1, formats: ["multiple_choice", "parsons"] }),
        DEFAULTS,
      ),
    ).toBe(6);
  });

  it("equals the counts when only one format is chosen", () => {
    expect(specTotal(spec({ easy: 1, medium: 2 }), DEFAULTS)).toBe(3);
  });

  it("multiplies by the inherited default when the row has no formats of its own", () => {
    expect(specTotal(spec({ hard: 2 }), ["coding", "debugging", "parsons"])).toBe(6);
  });

  it("is zero when nothing is asked for, whatever the formats", () => {
    expect(specTotal(spec({ formats: ["coding", "parsons"] }), DEFAULTS)).toBe(0);
  });
});

describe("effectiveFormats", () => {
  it("falls back to the sheet default when the chunk has no formats of its own", () => {
    expect(effectiveFormats(spec(), DEFAULTS)).toEqual(["multiple_choice"]);
  });

  it("uses the chunk's own formats once it has them", () => {
    expect(effectiveFormats(spec({ formats: ["coding"] }), DEFAULTS)).toEqual(["coding"]);
  });
});

describe("toRequestChunks", () => {
  it("sends a chunk's counts with the formats it inherits", () => {
    const chunks = toRequestChunks([row(7)], { 7: spec({ medium: 2 }) }, DEFAULTS);

    expect(chunks).toEqual([
      { section_id: 7, easy: 0, medium: 2, hard: 0, question_types: ["multiple_choice"] },
    ]);
  });

  it("sends a chunk's own formats in place of the default", () => {
    const chunks = toRequestChunks(
      [row(7)],
      { 7: spec({ hard: 1, formats: ["coding", "debugging"] }) },
      DEFAULTS,
    );

    expect(chunks[0].question_types).toEqual(["coding", "debugging"]);
  });

  it("leaves out rows that ask for nothing", () => {
    const chunks = toRequestChunks([row(7), row(8)], { 7: spec({ easy: 1 }) }, DEFAULTS);

    expect(chunks.map((chunk) => chunk.section_id)).toEqual([7]);
  });

  it("leaves out a chunk with no text, even when it was given counts", () => {
    const chunks = toRequestChunks(
      [row(7, { selectable: false })],
      { 7: spec({ easy: 3 }) },
      DEFAULTS,
    );

    expect(chunks).toEqual([]);
  });

  it("keeps the row order, so the run is generated in the order it is read", () => {
    const chunks = toRequestChunks(
      [row(9), row(4)],
      { 9: spec({ easy: 1 }), 4: spec({ easy: 1 }) },
      DEFAULTS,
    );

    expect(chunks.map((chunk) => chunk.section_id)).toEqual([9, 4]);
  });
});
