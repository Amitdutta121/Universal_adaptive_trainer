/**
 * `/experiments/learning-charts` — design prototype of the charts that can show a class is
 * learning: a learning curve on a fixed cohort, first against latest answer per subtopic, and
 * correctness at the same difficulty over time. Two datasets behind a switcher: a simulated class
 * that learns (`mock-learning.ts`) and a snapshot of CS189's answers (`cs189-snapshot.ts`). No
 * API, no LLM. `AppChrome` skips this path.
 */

import type { Metadata } from "next";
import { LearningChartsExperience } from "./learning-charts-experience";

export const metadata: Metadata = {
  title: "Learning charts — design prototype",
  description: "Three charts that can show a class is learning, on simulated and snapshot data.",
};

export default function LearningChartsExperimentPage() {
  return <LearningChartsExperience />;
}
