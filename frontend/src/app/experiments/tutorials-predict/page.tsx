/**
 * `/experiments/tutorials-predict` — variant E of the student tutorial prototypes: "Predict, then
 * reveal". No explanation up front; the student predicts what a short snippet does, sees what
 * really happens, and gets one sentence of insight. Mock data only (no API, no LLM). Like
 * `/experiments/student`, it sits outside the Instructor Studio: `AppChrome` skips `/experiments`,
 * so this route renders with its own small header and no auth gate.
 *
 * See `predict-experience.tsx` for the flow and `mock-data.ts` for the experiments and the
 * `range()` re-implementation the results are computed with.
 */

import type { Metadata } from "next";
import { PredictExperience } from "./predict-experience";

export const metadata: Metadata = {
  title: "Predict, then reveal — design prototype",
  description:
    "A mock-data prototype of a student tutorial that teaches Python range() by asking for a prediction first, for design review.",
};

export default function TutorialsPredictPage() {
  return <PredictExperience />;
}
