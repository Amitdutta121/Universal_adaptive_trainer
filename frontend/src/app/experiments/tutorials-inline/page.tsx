/**
 * `/experiments/tutorials-inline` — a standalone design prototype of variant C for the student
 * tutorials: no tutorial page at all, the help appears where the student got stuck (the result of a
 * wrong practice answer). Mock data only (no API, no LLM). `AppChrome` skips `/experiments`, so this
 * route renders with its own shell and no auth gate.
 *
 * See `tutorials-inline-experience.tsx` for the flow and `mock-data.ts` for the stand-in content.
 */

import type { Metadata } from "next";
import { TutorialsInlineExperience } from "./tutorials-inline-experience";

export const metadata: Metadata = {
  title: "Inline help — design prototype",
  description:
    "A mock-data prototype of tutorial help that appears inside a wrong practice answer, for design review.",
};

export default function TutorialsInlineExperimentPage() {
  return <TutorialsInlineExperience />;
}
