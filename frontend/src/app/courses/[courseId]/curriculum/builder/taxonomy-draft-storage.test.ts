import { beforeEach, describe, expect, it } from "vitest";
import { sampleDraft } from "./taxonomy-draft.fixtures";
import {
  clearDraft,
  draftKey,
  loadDrafts,
  parseStoredDraft,
  saveDraft,
} from "./taxonomy-draft-storage";

const LEGACY_KEY = "adaptive-trainer:taxonomy-draft:v1";
const ALPHA = { id: 1, label: "Alpha" };
const BETA = { id: 2, label: "Beta" };

const named = (label: string) => ({ ...sampleDraft(), label });

describe("draft storage", () => {
  beforeEach(() => window.localStorage.clear());

  it("round-trips a draft", () => {
    saveDraft(sampleDraft());

    const [only] = loadDrafts();
    expect(only?.draft).toEqual(sampleDraft());
    expect(only?.origin).toBeNull();
    expect(only?.key).toBe("new");
  });

  it("keeps one draft per taxonomy, so saving one never touches another", () => {
    saveDraft(named("new one"));
    saveDraft(named("alpha one"), ALPHA);
    saveDraft(named("beta one"), BETA);

    expect(
      loadDrafts()
        .map((d) => d.draft.label)
        .sort(),
    ).toEqual(["alpha one", "beta one", "new one"]);

    saveDraft(named("alpha two"), ALPHA);
    const labels = Object.fromEntries(loadDrafts().map((d) => [d.key, d.draft.label]));
    expect(labels).toEqual({ new: "new one", v1: "alpha two", v2: "beta one" });
  });

  it("forgets only the draft it is asked to", () => {
    saveDraft(named("new one"));
    saveDraft(named("alpha one"), ALPHA);

    clearDraft(ALPHA);

    expect(loadDrafts().map((d) => d.key)).toEqual(["new"]);
    clearDraft(null);
    expect(loadDrafts()).toEqual([]);
    expect(window.localStorage.getItem("adaptive-trainer:taxonomy-drafts:v2")).toBeNull();
  });

  it("lists the most recently edited draft first", () => {
    saveDraft(named("first"), ALPHA);
    const stamp = JSON.parse(
      window.localStorage.getItem("adaptive-trainer:taxonomy-drafts:v2") ?? "{}",
    );
    stamp.v1.savedAt = "2020-01-01T00:00:00.000Z";
    window.localStorage.setItem("adaptive-trainer:taxonomy-drafts:v2", JSON.stringify(stamp));
    saveDraft(named("second"), BETA);

    expect(loadDrafts().map((d) => d.draft.label)).toEqual(["second", "first"]);
  });

  it("names the slot after the taxonomy a draft is a copy of", () => {
    expect(draftKey(null)).toBe("new");
    expect(draftKey(ALPHA)).toBe("v1");
  });

  it("moves the single draft an older version kept into its own slot, once, without losing it", () => {
    window.localStorage.setItem(
      LEGACY_KEY,
      JSON.stringify({ savedAt: "2026-01-01T00:00:00Z", origin: ALPHA, draft: sampleDraft() }),
    );

    const [migrated] = loadDrafts();

    expect(migrated?.key).toBe("v1");
    expect(migrated?.draft).toEqual(sampleDraft());
    expect(window.localStorage.getItem(LEGACY_KEY)).toBeNull();
    expect(loadDrafts()).toHaveLength(1);
  });

  it("does not let an older draft overwrite one already kept for the same taxonomy", () => {
    saveDraft(named("current"), ALPHA);
    window.localStorage.setItem(
      LEGACY_KEY,
      JSON.stringify({ savedAt: "2020-01-01T00:00:00Z", origin: ALPHA, draft: named("stale") }),
    );

    expect(loadDrafts().map((d) => d.draft.label)).toEqual(["current"]);
  });

  it("drops what it did not write instead of trusting it into the editor", () => {
    expect(parseStoredDraft(null)).toBeNull();
    expect(parseStoredDraft("not json")).toBeNull();
    expect(parseStoredDraft("[]")).toBeNull();
    expect(
      parseStoredDraft(JSON.stringify({ savedAt: "x", draft: { label: 1, topics: [] } })),
    ).toBeNull();
    // A topic missing its id, as an older shape might be.
    const bad = {
      savedAt: "x",
      draft: { label: "L", topics: [{ name: "T", description: "", subtopics: [] }] },
    };
    expect(parseStoredDraft(JSON.stringify(bad))).toBeNull();
    // A subtopic with a non-string name.
    const worse = {
      savedAt: "x",
      draft: {
        label: "L",
        topics: [
          {
            id: "t",
            name: "T",
            description: "",
            subtopics: [{ id: "s", name: 3, description: "" }],
          },
        ],
      },
    };
    expect(parseStoredDraft(JSON.stringify(worse))).toBeNull();
  });

  it("ignores a slot that is damaged and keeps the others", () => {
    window.localStorage.setItem(
      "adaptive-trainer:taxonomy-drafts:v2",
      JSON.stringify({
        new: { savedAt: "x", draft: { label: "fine", topics: [] }, origin: null },
        v9: { savedAt: "x", draft: "garbage" },
      }),
    );

    expect(loadDrafts().map((d) => d.key)).toEqual(["new"]);
  });

  it("does not throw when storage is unavailable", () => {
    const original = Object.getOwnPropertyDescriptor(window, "localStorage");
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get() {
        throw new Error("blocked");
      },
    });
    try {
      expect(() => saveDraft(sampleDraft())).not.toThrow();
      expect(() => clearDraft(null)).not.toThrow();
      expect(loadDrafts()).toEqual([]);
    } finally {
      if (original) Object.defineProperty(window, "localStorage", original);
    }
  });
});
