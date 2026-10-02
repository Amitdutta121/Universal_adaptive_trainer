/**
 * `/experiments/tutorials-trace` — variant B of the short student tutorial: a code snippet you step
 * through, with live variables and output, on mock data only (no API, no LLM). Like the other
 * prototypes it sits outside the Instructor Studio: `AppChrome` skips `/experiments`, so this route
 * renders standalone with no auth gate.
 *
 * See `tutorials-trace-experience.tsx` for the flow and `mock-data.ts` for the recorded traces.
 */

import type { Metadata } from "next";
import { TutorialsTraceExperience } from "./tutorials-trace-experience";

export const metadata: Metadata = {
  title: "Tutorial B: code tracer — design prototype",
  description: "A mock-data prototype of a step-through code tracer for a short for-loop tutorial.",
};

export default function TutorialsTraceExperimentPage() {
  return <TutorialsTraceExperience />;
}
