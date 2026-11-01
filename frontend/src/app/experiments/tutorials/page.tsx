/**
 * `/experiments/tutorials` — a standalone design prototype of the student-facing tutorials, on mock
 * data only (no API, no LLM). Like `/experiments/student`, `AppChrome` skips this path, so it renders
 * with its own shell and no auth gate.
 *
 * See `tutorials-experience.tsx` for the page and `mock-tutorials.ts` for the stand-in content.
 */

import type { Metadata } from "next";
import { TutorialsExperience } from "./tutorials-experience";

export const metadata: Metadata = {
  title: "Tutorials — design prototype",
  description: "A mock-data prototype of the student tutorial reader, for design review.",
};

export default function TutorialsExperimentPage() {
  return <TutorialsExperience />;
}
