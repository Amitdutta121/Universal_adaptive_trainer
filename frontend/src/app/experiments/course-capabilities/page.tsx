/**
 * `/experiments/course-capabilities` — design prototypes of the course capabilities setup: pick a
 * subject preset, enable grading capabilities, and see which question types that allows. Three
 * versions behind one switcher, on mock data only (no API, no LLM). `AppChrome` skips this path.
 *
 * See `capabilities-experience.tsx` for the switcher and `mock-capabilities.ts` for the data.
 */

import type { Metadata } from "next";
import { Suspense } from "react";
import { CapabilitiesExperience } from "./capabilities-experience";

export const metadata: Metadata = {
  title: "Course capabilities — design prototype",
  description: "Three mock-data versions of the course capabilities setup, for design review.",
};

export default function CourseCapabilitiesExperimentPage() {
  return (
    <Suspense>
      <CapabilitiesExperience />
    </Suspense>
  );
}
