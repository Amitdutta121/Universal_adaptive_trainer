/**
 * `/experiments/question-setup` — design prototype of the question setup wizard a professor sees
 * after importing a book and approving a taxonomy: mine the book, approve or skip suggested
 * question styles, review the chosen styles, then a subtopic x difficulty plan. Three courses
 * (Python, physics, biology) behind one switcher, on mock data only (no API, no LLM).
 * `AppChrome` skips this path.
 */

import type { Metadata } from "next";
import { Suspense } from "react";
import { QuestionSetupExperience } from "./question-setup-experience";

export const metadata: Metadata = {
  title: "Question setup — design prototype",
  description: "Mock-data question setup wizard: mine the book, choose question styles, plan generation.",
};

export default function QuestionSetupExperimentPage() {
  return (
    <Suspense>
      <QuestionSetupExperience />
    </Suspense>
  );
}
