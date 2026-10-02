/**
 * `/experiments/tutorials-practice` — a standalone design prototype of variant G for the student
 * tutorials: no tutorial page, the practice flow IS the tutorial. Help is a ladder that opens only
 * when the student asks or misses: a one-line hint, then a step-through simulator of the question's
 * own code, then a worked and a faded example. Mock data only (no API, no LLM). `AppChrome` skips
 * `/experiments`, so this route renders with its own shell and no auth gate.
 *
 * See `tutorials-practice-experience.tsx` for the flow, `mock-data.ts` for the stand-in content and
 * `mini-python/` for the small Python runner behind the simulator.
 */

import type { Metadata } from "next";
import { TutorialsPracticeExperience } from "./tutorials-practice-experience";

export const metadata: Metadata = {
  title: "Practice first — design prototype",
  description:
    "A mock-data prototype of practice-first tutorials with a step-through simulator on demand, for design review.",
};

export default function TutorialsPracticeExperimentPage() {
  return <TutorialsPracticeExperience />;
}
