/**
 * Every per-question-type UI piece, behind one lookup.
 *
 * A screen never branches on a `question_type` string: it reads the type's entry here and
 * renders what the entry hands it. Adding a type means adding one file next to this one and
 * one line in `QUESTION_TYPE_UI`. An entry of `null` is a type the backend knows about whose
 * UI is not built yet; screens treat it like an unknown type.
 */

import type React from "react";
import type {
  QuestionDetail,
  QuestionKind,
  QuestionType,
  ServedQuestionOut,
} from "@/lib/api/types";
import { codeCompletion } from "./code-completion";
import { coding } from "./coding";
import { debugging } from "./debugging";
import { equationResponse } from "./equation-response";
import { multipleChoice } from "./multiple-choice";
import { numericResponse } from "./numeric-response";
import { outputPrediction } from "./output-prediction";
import { parsons } from "./parsons";
import { trueFalse } from "./true-false";

/** The question as the student is served it: no answer key. */
export type StudentQuestion = ServedQuestionOut;

/** The stored `content` dict, answer key included. */
export type QuestionContent = NonNullable<QuestionDetail["content"]>;

/**
 * Every type id the registry is keyed by. `numeric_response` and `equation_response` are
 * listed explicitly because the backend adds them (T0a) before `schema.d.ts` is regenerated;
 * once it is, they are already members of `QuestionType` and this union collapses into it.
 */
export type RegistryQuestionType = QuestionType | "numeric_response" | "equation_response";

export type AnswerInputProps = {
  question: StudentQuestion;
  value: string;
  onChange(v: string): void;
  /** Free-text inputs submit on Ctrl/Cmd+Enter; the others ignore it. */
  onSubmit?(): void;
};

export type ReviewContentProps = {
  content: QuestionContent;
  /** What the student submitted, when the screen still knows it (not for past attempts). */
  submittedAnswer?: string;
};

/** The instructor review page's per-type body: answer key, checks, and inline editing. */
export type AuthoringReviewProps = {
  detail: QuestionDetail;
  isInlineEditing: boolean;
  promptEdit: string;
  referenceEdit: string;
  testsEdit: string;
  onPromptEdit: (value: string) => void;
  onReferenceEdit: (value: string) => void;
  onTestsEdit: (value: string) => void;
};

export type QuestionTypeUI = {
  /** Full display name ("Multiple choice"). */
  label: string;
  /** Short display name for tight rows ("MCQ"). */
  shortLabel: string;
  answerLabel: string;
  AnswerInput: React.FC<AnswerInputProps>;
  /** What was correct, shown to the student once the question is answered. */
  ReviewContent: React.FC<ReviewContentProps>;
  /**
   * Whether the student review also shows the stored reference solution and tests. Only the
   * executable types carry information there that `ReviewContent` does not already show.
   */
  showReferenceSolution?: boolean;
  /** Shown next to the type in the generate controls (kept as it was displayed before T0b). */
  kind: QuestionKind;
  /** Has distractor options, so "poor distractors" is a reason a reviewer may give. */
  hasDistractors?: boolean;
  /** Has executable tests, so test-related rejection reasons apply. */
  hasTests?: boolean;
  AuthoringReview: React.FC<AuthoringReviewProps>;
};

/** Insertion order is the canonical order every type picker and filter uses. */
export const QUESTION_TYPE_UI: Record<RegistryQuestionType, QuestionTypeUI | null> = {
  multiple_choice: multipleChoice,
  true_false: trueFalse,
  output_prediction: outputPrediction,
  code_completion: codeCompletion,
  debugging: debugging,
  parsons: parsons,
  coding: coding,
  numeric_response: numericResponse,
  equation_response: equationResponse,
};

/** The registry entry for a type, or null when the type is absent, unknown or not built. */
export function questionTypeUI(
  questionType: RegistryQuestionType | null | undefined,
): QuestionTypeUI | null {
  return questionType ? (QUESTION_TYPE_UI[questionType] ?? null) : null;
}

/** The types with a built UI, in canonical order. */
export const BUILT_QUESTION_TYPES: readonly QuestionType[] = (
  Object.keys(QUESTION_TYPE_UI) as RegistryQuestionType[]
).filter((type): type is QuestionType => QUESTION_TYPE_UI[type] !== null);

/** Display name for any type; an unbuilt one falls back to its id with spaces. */
export function questionTypeLabel(questionType: RegistryQuestionType): string {
  return QUESTION_TYPE_UI[questionType]?.label ?? questionType.replace(/_/g, " ");
}

/** Short display name for any type; an unbuilt one falls back to its id with spaces. */
export function questionTypeShortLabel(questionType: RegistryQuestionType): string {
  return QUESTION_TYPE_UI[questionType]?.shortLabel ?? questionType.replace(/_/g, " ");
}
