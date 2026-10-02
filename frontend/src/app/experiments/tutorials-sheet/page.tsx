/**
 * `/experiments/tutorials-sheet` — variant D of the short-tutorial prototypes: a one-screen
 * cheat sheet ("in 60 seconds") for Python `for` loops with `range()`. Mock data only (no API,
 * no LLM). Like the other prototypes it sits outside the Instructor Studio: `AppChrome` skips
 * `/experiments`, so it renders with its own shell and no auth gate.
 *
 * See `tutorials-sheet-experience.tsx` for the layout and `mock-data.ts` for the stand-in
 * content that a real pipeline (patterns extracted from the book section, approved by the
 * professor) would replace.
 */

import type { Metadata } from "next";
import { TutorialsSheetExperience } from "./tutorials-sheet-experience";

export const metadata: Metadata = {
  title: "Cheat sheet tutorial — design prototype",
  description: "A mock-data, one-screen cheat sheet for Python for loops and range(), for design review.",
};

export default function TutorialsSheetPage() {
  return <TutorialsSheetExperience />;
}
