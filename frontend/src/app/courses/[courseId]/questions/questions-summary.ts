/**
 * The questions page subtitle, worded for the open course's subject.
 *
 * The app serves any subject, so the subtitle names the course's own subject
 * preset rather than a fixed one. A course on the "custom" preset, or one whose
 * course or catalog has not loaded yet, gets the neutral wording.
 */

import type { Schemas } from "@/lib/api/types";

const NEUTRAL = "Generate, validate and review assessment questions.";

/** The label of `subjectId` in the catalog, or `null` when there is nothing to name. */
export function subjectLabel(
  subjectId: string | undefined,
  subjects: Pick<Schemas["SubjectPresetOut"], "id" | "label">[] | undefined,
): string | null {
  if (!subjectId || subjectId === "custom") return null;
  return subjects?.find((entry) => entry.id === subjectId)?.label ?? null;
}

export function questionsSummary(label: string | null): string {
  return label ? `Generate, validate and review assessment questions for ${label}.` : NEUTRAL;
}
