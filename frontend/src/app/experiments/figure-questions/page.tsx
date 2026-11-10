/**
 * `/experiments/figure-questions` — design prototype of questions with figures on the student
 * side: Mermaid diagrams, Chart.js charts, and computed SVGs with per-student variants. Uses the
 * real answer widgets from the question-type registry. No API, no LLM.
 */

import type { Metadata } from "next";
import { FigureQuestionsExperience } from "./figure-questions-experience";

export const metadata: Metadata = {
  title: "Figure questions — design prototype",
  description: "Questions with diagrams, charts and computed figures, as a student sees them.",
};

export default function FigureQuestionsExperimentPage() {
  return <FigureQuestionsExperience />;
}
