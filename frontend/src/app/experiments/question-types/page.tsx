/**
 * `/experiments/question-types` — design prototype of the type-first question setup for a new
 * Intro Python course: question types, the real style library behind each, per-subtopic
 * adjustments, the turn-off / turn-on dialogs, targets and course Settings. No API, no LLM.
 */

import type { Metadata } from "next";
import { Suspense } from "react";
import { QuestionTypesExperience } from "./question-types-experience";

export const metadata: Metadata = {
  title: "Question types — design prototype",
  description: "Type-first question setup: types, styles, subtopic adjustments, targets.",
};

export default function QuestionTypesExperimentPage() {
  return (
    <Suspense>
      <QuestionTypesExperience />
    </Suspense>
  );
}
