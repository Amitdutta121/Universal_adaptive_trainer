/**
 * `/experiments/tutorials-deck` — a standalone design prototype of the final student tutorial
 * round: short cards, a live step-through simulator with optional predict-first, and a faded
 * completion, for five topics. Mock data only (no API, no LLM); the traces were recorded from real
 * Python. `AppChrome` skips `/experiments`, so this route renders with its own shell and no auth gate.
 *
 * See `deck-experience.tsx` for the flow and `mock-data.ts` for the stand-in content.
 */

import type { Metadata } from "next";
import { DeckExperience } from "./deck-experience";

export const metadata: Metadata = {
  title: "Trace-lesson deck — design prototype",
  description:
    "A mock-data prototype of short tutorial decks with a live code simulator, for design review.",
};

export default function TutorialsDeckExperimentPage() {
  return <DeckExperience />;
}
