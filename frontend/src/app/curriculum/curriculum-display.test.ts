/**
 * The wording and the gate that ADR-021 makes load-bearing.
 *
 * Two things are pinned. First, that every status the backend can send has a
 * label, a variant and a meaning — a status added to the enum must fail here
 * rather than render as a blank badge. Second, that the taxonomy-upload gate
 * answers `false` for a legacy row, including one that recorded no generator at
 * all: getting that backwards would hide evidence a legacy subtopic really has,
 * or imply an uploaded one has evidence it never claimed.
 */

import { describe, expect, it } from "vitest";
import type { CurriculumItemStatus, CurriculumStatus } from "@/lib/api/types";
import {
  CONFIDENCE_VARIANT,
  CURRICULUM_ITEM_STATUS_LABEL,
  CURRICULUM_ITEM_STATUS_VARIANT,
  CURRICULUM_STATUS_LABEL,
  CURRICULUM_STATUS_MEANING,
  CURRICULUM_STATUS_VARIANT,
  generatedByLabel,
  isTaxonomyUpload,
  STANDING_LABEL,
  STANDING_MEANING,
  STANDING_VARIANT,
  stableIdMeaning,
  TAXONOMY_UPLOAD_GENERATOR,
  versionStanding,
} from "./curriculum-display";

const STATUSES: CurriculumStatus[] = ["approved", "superseded", "proposed", "under_review"];
const ITEM_STATUSES: CurriculumItemStatus[] = ["accepted", "edited", "proposed", "rejected"];

describe("status maps", () => {
  it("covers every version status the backend can send", () => {
    for (const map of [
      CURRICULUM_STATUS_LABEL,
      CURRICULUM_STATUS_VARIANT,
      CURRICULUM_STATUS_MEANING,
    ]) {
      expect(Object.keys(map).sort()).toEqual([...STATUSES].sort());
    }
  });

  it("covers every item status the backend can send", () => {
    for (const map of [CURRICULUM_ITEM_STATUS_LABEL, CURRICULUM_ITEM_STATUS_VARIANT]) {
      expect(Object.keys(map).sort()).toEqual([...ITEM_STATUSES].sort());
    }
  });

  it("treats no version status as a failure", () => {
    // `superseded` is history, not damage — a destructive badge would read as one.
    expect(Object.values(CURRICULUM_STATUS_VARIANT)).not.toContain("destructive");
  });

  it("marks a rejected item, which is the one real negative", () => {
    expect(CURRICULUM_ITEM_STATUS_VARIANT.rejected).toBe("destructive");
  });

  it("reserves the destructive confidence badge for low", () => {
    expect(CONFIDENCE_VARIANT.low).toBe("destructive");
    expect(CONFIDENCE_VARIANT.high).not.toBe("destructive");
  });
});

describe("isTaxonomyUpload", () => {
  it("recognises an uploaded taxonomy", () => {
    expect(isTaxonomyUpload({ generated_by: TAXONOMY_UPLOAD_GENERATOR })).toBe(true);
  });

  it("does not treat a legacy proposal as one", () => {
    expect(isTaxonomyUpload({ generated_by: "deepseek/deepseek-chat" })).toBe(false);
  });

  it("does not treat an unrecorded generator as one", () => {
    // A legacy row with no generator still has evidence worth showing.
    expect(isTaxonomyUpload({ generated_by: null })).toBe(false);
  });
});

describe("generatedByLabel", () => {
  it("names an upload in words", () => {
    expect(generatedByLabel({ generated_by: TAXONOMY_UPLOAD_GENERATOR })).toBe("Uploaded taxonomy");
  });

  it("shows the model for a legacy row", () => {
    expect(generatedByLabel({ generated_by: "deepseek/deepseek-chat" })).toBe(
      "deepseek/deepseek-chat",
    );
  });

  it("never renders a missing generator as text", () => {
    expect(generatedByLabel({ generated_by: null })).toBe("—");
    expect(generatedByLabel({ generated_by: "  " })).toBe("—");
  });
});

describe("stableIdMeaning", () => {
  it("does not mention evidence for an uploaded taxonomy", () => {
    // ADR-021: a taxonomy page must not imply an upload carries evidence.
    const meaning = stableIdMeaning(true);
    expect(meaning).not.toMatch(/evidence|source material/);
  });

  it("explains the evidence link for a legacy subtopic", () => {
    expect(stableIdMeaning(false)).toMatch(/evidence/);
  });
});

describe("versionStanding", () => {
  it("calls the live version live", () => {
    expect(versionStanding({ id: 3, status: "approved" }, 3)).toBe("live");
  });

  it("calls an older approved version replaced, not approved", () => {
    // The load-bearing case: nothing ever writes `superseded`, so every upload
    // stays `approved` forever. Badging them all the same would tell a professor
    // that generation is grounded in a taxonomy it stopped using.
    expect(versionStanding({ id: 1, status: "approved" }, 3)).toBe("replaced");
  });

  it("says replaced rather than live when nothing is approved", () => {
    expect(versionStanding({ id: 1, status: "approved" }, null)).toBe("replaced");
    expect(versionStanding({ id: 1, status: "approved" }, undefined)).toBe("replaced");
  });

  it("passes a legacy status through untouched", () => {
    expect(versionStanding({ id: 1, status: "proposed" }, 3)).toBe("proposed");
    expect(versionStanding({ id: 1, status: "under_review" }, 3)).toBe("under_review");
  });

  it("labels every standing it can return", () => {
    for (const standing of ["live", "replaced", "proposed", "under_review"] as const) {
      expect(STANDING_LABEL[standing]).toBeTruthy();
      expect(STANDING_VARIANT[standing]).toBeTruthy();
      expect(STANDING_MEANING[standing]).toBeTruthy();
    }
  });

  it("claims generation is grounded only in the live one", () => {
    expect(STANDING_MEANING.live).toMatch(/grounded/);
    expect(STANDING_MEANING.replaced).not.toMatch(/grounded/);
  });
});
