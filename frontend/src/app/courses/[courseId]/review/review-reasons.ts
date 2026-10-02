/**
 * Which rejection reasons a reviewer may give for a question type.
 *
 * Kept out of review-utils.ts on purpose: the per-type files in lib/question-types import
 * review-utils, so review-utils must not import the registry. That import cycle left a type's
 * registry entry undefined whenever the type file happened to load before the registry.
 */
import { questionTypeUI } from "@/lib/question-types/registry";
import type { QuestionDetail, RejectionReason } from "./review-types";
import { REJECTION_REASONS } from "./review-types";

export function reviewReasonOptions(
  questionType: QuestionDetail["question"]["question_type"],
): RejectionReason[] {
  const ui = questionTypeUI(questionType);
  const base = REJECTION_REASONS.filter((reason) => reason !== "poor_distractors");
  if (ui?.hasDistractors) return REJECTION_REASONS.slice();
  return base.filter(
    (reason) => !((reason === "incorrect_tests" || reason === "poor_tests") && !ui?.hasTests),
  );
}
