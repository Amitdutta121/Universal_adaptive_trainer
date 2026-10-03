/**
 * Shapes shared by the question-setup screens (docs/QUESTION_SETUP_PLAN.md): the setup modal
 * on the Questions page and the design prototype under `app/experiments/question-setup`.
 */

import type { Difficulty } from "@/lib/api/types";

export type { Difficulty };

export const DIFFICULTIES: readonly Difficulty[] = ["easy", "medium", "hard"];

export const DIFFICULTY_LABEL: Record<Difficulty, string> = {
  easy: "Easy",
  medium: "Medium",
  hard: "Hard",
};

/**
 * One example question shown on a style card. The professor sees the answer key.
 *
 * Structural on purpose: the API's `ExampleQuestion` (nullable fields, empty lists by default)
 * and the prototype's hand-written examples both fit it.
 */
export interface ExampleQuestion {
  prompt: string;
  /** A code listing shown under the prompt. */
  code?: string | null;
  /** Choice options; `correct` marks the key. */
  options?: readonly { text: string; correct?: boolean }[];
  /** Parsons: the solution lines in their correct order (shown shuffled to the student). */
  lines?: readonly string[];
  /** The answer key in words: expected output, value with unit, expression, accepted text. */
  answer?: string | null;
  /** Hidden test count, for code types graded by tests. */
  tests?: number | null;
  /** The book section the example is grounded in. */
  grounding: string;
}
