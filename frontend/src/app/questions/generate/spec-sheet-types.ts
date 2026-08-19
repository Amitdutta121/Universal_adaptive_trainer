/**
 * The vocabulary of the spec sheet: what a chunk asks for, and what a row shows.
 *
 * Pure. No React, no fetching. Everything here is either a name for something the
 * backend already models or a shaping helper with no rule in it — the rule that
 * turns counts into questions lives in the API (ADR-044) and is read from
 * `/api/questions/batch-plan`.
 */

import type { Difficulty, QuestionType, Schemas } from "@/lib/api/types";

export type GenerationPlanResponse = Schemas["GenerationPlanResponse"];
export type ChunkGenerationSpec = Schemas["ChunkGenerationSpec"];
export type BatchPlanTotals = Schemas["BatchPlanTotals"];
export type BookSummary = Schemas["BookSummary"];

/** The three difficulty columns, in the order the compiled run walks them. */
export const DIFFICULTIES = ["easy", "medium", "hard"] as const satisfies readonly Difficulty[];

export const QUESTION_TYPES = [
  "multiple_choice",
  "true_false",
  "output_prediction",
  "code_completion",
  "debugging",
  "parsons",
  "coding",
] as const satisfies readonly QuestionType[];

export const QUESTION_TYPE_LABEL: Record<QuestionType, string> = {
  multiple_choice: "Multiple choice",
  true_false: "True / false",
  output_prediction: "Output prediction",
  code_completion: "Code completion",
  debugging: "Debugging",
  parsons: "Parsons",
  coding: "Coding",
};

/** Short forms for the row, where a full label would not fit. */
export const QUESTION_TYPE_SHORT: Record<QuestionType, string> = {
  multiple_choice: "MCQ",
  true_false: "T/F",
  output_prediction: "Output",
  code_completion: "Completion",
  debugging: "Debugging",
  parsons: "Parsons",
  coding: "Coding",
};

/** The highest count one stepper offers, matching the API's per-difficulty bound. */
export const MAX_COUNT_PER_DIFFICULTY = 20;

/**
 * What one chunk asks for.
 *
 * Each count applies to *every* chosen format, so a chunk produces
 * `(easy + medium + hard) x formats` questions.
 *
 * `formats: null` means the chunk has not been given its own formats and follows
 * the sheet default. Keeping "inherited" distinct from "happens to equal the
 * default" is what lets the sheet show which rows a professor actually touched.
 */
export interface ChunkSpec {
  easy: number;
  medium: number;
  hard: number;
  formats: QuestionType[] | null;
}

export const EMPTY_SPEC: ChunkSpec = { easy: 0, medium: 0, hard: 0, formats: null };

/** Specs by section id. A section with no entry asks for nothing. */
export type ChunkSpecMap = Readonly<Record<number, ChunkSpec>>;

/** One chunk, flattened out of its book and chapter for the table. */
export interface SheetRow {
  sectionId: number;
  bookId: number;
  bookTitle: string;
  chapterId: number;
  chapterLabel: string;
  title: string;
  locationLabel: string | null;
  charCount: number;
  existingQuestionCount: number;
  /** False for a chunk with no text: the generator would receive nothing. */
  selectable: boolean;
  /** No heading was declared in the source; the label is its printed location. */
  isUnlabelled: boolean;
}

/** The formats a chunk will actually use: its own, or the sheet default. */
export const effectiveFormats = (
  spec: ChunkSpec,
  sheetDefault: readonly QuestionType[],
): readonly QuestionType[] => spec.formats ?? sheetDefault;

export const countFor = (spec: ChunkSpec, difficulty: Difficulty): number => spec[difficulty];

/** The counts added up: how many questions this chunk asks for *per format*. */
export const specPerFormatTotal = (spec: ChunkSpec): number => spec.easy + spec.medium + spec.hard;

/**
 * How many questions this chunk contributes in total.
 *
 * Mirrors `ChunkQuestionRequest.total` on the backend, which stays the authority:
 * the sheet needs a per-row number before the whole sheet is priced, and a row
 * that disagreed with the API's arithmetic would be worse than no row total.
 */
export const specTotal = (spec: ChunkSpec, sheetDefault: readonly QuestionType[]): number =>
  specPerFormatTotal(spec) * effectiveFormats(spec, sheetDefault).length;

/**
 * Shape the sheet into the request body.
 *
 * Only chunks that ask for something are sent. Rows the professor never touched,
 * and rows the plan marked unusable, are left out rather than being sent as zeroes.
 */
export function toRequestChunks(
  rows: readonly SheetRow[],
  specs: ChunkSpecMap,
  sheetDefault: readonly QuestionType[],
): ChunkGenerationSpec[] {
  return rows.flatMap((row) => {
    const spec = specs[row.sectionId];
    if (!spec || specPerFormatTotal(spec) === 0 || !row.selectable) return [];
    return [
      {
        section_id: row.sectionId,
        easy: spec.easy,
        medium: spec.medium,
        hard: spec.hard,
        question_types: [...effectiveFormats(spec, sheetDefault)],
      },
    ];
  });
}

/** "pp. 88-91", "p. 97", or the plan's own label when there is no page range. */
export function pageLabel(row: SheetRow): string {
  return row.locationLabel ?? "-";
}
