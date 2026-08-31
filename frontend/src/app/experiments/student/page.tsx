/**
 * `/experiments/student` — a standalone design prototype of the student-facing
 * adaptive practice flow, on mock data only (no API, no LLM). It is intentionally
 * outside the Instructor Studio: `AppChrome` skips `/experiments`, so this route
 * renders with its own full-page shell and no auth gate.
 *
 * See `student-experience.tsx` for the flow and `mock-data.ts` for the stand-in
 * selection / scoring / mastery logic that a real query layer would replace.
 */

import type { Metadata } from "next";
import { StudentExperience } from "./student-experience";

export const metadata: Metadata = {
  title: "Student experience — design prototype",
  description: "A mock-data prototype of the adaptive student practice flow, for design review.",
};

export default function StudentExperimentPage() {
  return <StudentExperience />;
}
