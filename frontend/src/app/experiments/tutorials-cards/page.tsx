/**
 * `/experiments/tutorials-cards` — variant A of the short student tutorial: a micro-card stepper,
 * one idea per screen, mock data only (no API, no LLM). Like `/experiments/tutorials`, `AppChrome`
 * skips this path, so it renders with its own shell and no auth gate.
 *
 * See `cards-experience.tsx` for the flow and `mock-data.ts` for the stand-in lesson content.
 */

import type { Metadata } from "next";
import { CardsExperience } from "./cards-experience";

export const metadata: Metadata = {
  title: "Tutorial cards — design prototype",
  description: "A mock-data prototype of a one-idea-per-screen tutorial stepper, for design review.",
};

export default function TutorialCardsExperimentPage() {
  return <CardsExperience />;
}
