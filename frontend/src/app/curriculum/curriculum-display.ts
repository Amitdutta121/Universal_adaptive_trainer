/**
 * How a curriculum row is labelled on screen.
 *
 * Pure, and separate from the components, so the wording that carries meaning —
 * `superseded` is history, not damage — is decided in one place and can be tested
 * without rendering anything.
 *
 * The gate below is the load-bearing one. ADR-021 says a taxonomy page must not
 * imply that an uploaded subtopic carries textbook evidence, a grouping rationale
 * or model metadata. An uploaded version has none of those, so the sections that
 * would show them are not emptied — they are not rendered at all.
 */

import type {
  ConceptConfidence,
  CurriculumItemStatus,
  CurriculumStatus,
  CurriculumVersionSummary,
} from "@/lib/api/types";

/** What `generated_by` reads for a version a professor uploaded. */
export const TAXONOMY_UPLOAD_GENERATOR = "taxonomy-upload";

export const CURRICULUM_STATUS_LABEL: Record<CurriculumStatus, string> = {
  approved: "approved",
  superseded: "superseded",
  proposed: "proposed",
  under_review: "under review",
};

/** None of the four is a failure, so none of them is `destructive`. */
export const CURRICULUM_STATUS_VARIANT: Record<CurriculumStatus, "secondary" | "outline"> = {
  approved: "secondary",
  superseded: "outline",
  proposed: "outline",
  under_review: "outline",
};

export const CURRICULUM_STATUS_MEANING: Record<CurriculumStatus, string> = {
  approved: "Question generation is grounded in this version.",
  superseded:
    "A later upload replaced it. Questions generated from it keep their taxonomy claim.",
  proposed: "A legacy proposal that was never approved. Nothing generates from it.",
  under_review: "A legacy proposal part-way through review. Nothing generates from it.",
};

export const CURRICULUM_ITEM_STATUS_LABEL: Record<CurriculumItemStatus, string> = {
  accepted: "accepted",
  edited: "edited",
  proposed: "proposed",
  rejected: "rejected",
};

/** `rejected` is the one genuinely negative value here. */
export const CURRICULUM_ITEM_STATUS_VARIANT: Record<
  CurriculumItemStatus,
  "secondary" | "outline" | "destructive"
> = {
  accepted: "secondary",
  edited: "outline",
  proposed: "outline",
  rejected: "destructive",
};

export const CONFIDENCE_VARIANT: Record<
  ConceptConfidence,
  "secondary" | "outline" | "destructive"
> = {
  high: "secondary",
  medium: "outline",
  low: "destructive",
};

/**
 * What a version's standing actually is, given which one is live.
 *
 * The status column cannot be read straight from `status`. An upload is written
 * `approved` and **nothing ever supersedes it** — `get_approved()` simply takes
 * the newest — so after three uploads all three rows say `approved` while only
 * one grounds anything. Badging all three the same would tell a professor that
 * generation uses a taxonomy it does not.
 *
 * `approvedVersionId` comes from the list response, which names the live one.
 */
export type VersionStanding = "live" | "replaced" | CurriculumStatus;

export function versionStanding(
  version: Pick<CurriculumVersionSummary, "id" | "status">,
  approvedVersionId: number | null | undefined,
): VersionStanding {
  if (version.status !== "approved") return version.status;
  return version.id === approvedVersionId ? "live" : "replaced";
}

export const STANDING_LABEL: Record<VersionStanding, string> = {
  ...CURRICULUM_STATUS_LABEL,
  live: "in use",
  replaced: "replaced",
};

export const STANDING_VARIANT: Record<VersionStanding, "secondary" | "outline"> = {
  ...CURRICULUM_STATUS_VARIANT,
  live: "secondary",
  replaced: "outline",
};

export const STANDING_MEANING: Record<VersionStanding, string> = {
  ...CURRICULUM_STATUS_MEANING,
  live: "Question generation and coverage are grounded in this version.",
  replaced:
    "A later upload took over. It is still marked approved, and questions generated from it keep their taxonomy claim.",
};

/**
 * Whether this version is an uploaded fixed taxonomy rather than a legacy proposal.
 *
 * The gate for every evidence, rationale and model-metadata section on these
 * pages. A `null` generator is *not* an upload: a legacy row that recorded no
 * generator must keep showing the evidence it really has.
 */
export function isTaxonomyUpload(version: Pick<CurriculumVersionSummary, "generated_by">): boolean {
  return version.generated_by === TAXONOMY_UPLOAD_GENERATOR;
}

/** How a version was produced, in words — never the string "null". */
export function generatedByLabel(
  version: Pick<CurriculumVersionSummary, "generated_by">,
): string {
  if (isTaxonomyUpload(version)) return "Uploaded taxonomy";
  return version.generated_by?.trim() || "—";
}

/**
 * Why a stable id exists, worded for the provenance the row actually has.
 *
 * The upload wording must not mention evidence or source material: an uploaded
 * subtopic has neither, and saying so would imply it does (ADR-021).
 */
export function stableIdMeaning(fromUpload: boolean): string {
  return fromUpload
    ? "The stable id preserves this subtopic's identity if its display name is edited later."
    : "The stable id is derived from the source material this subtopic was built from, not from " +
        "its name, so renaming it will not detach its evidence or its weakness tracking.";
}
