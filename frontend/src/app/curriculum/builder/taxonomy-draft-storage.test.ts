import { beforeEach, describe, expect, it } from "vitest";
import { sampleDraft } from "./taxonomy-draft.fixtures";
import { clearDraft, loadDraft, parseStoredDraft, saveDraft } from "./taxonomy-draft-storage";

describe("draft storage", () => {
  beforeEach(() => window.localStorage.clear());

  it("round-trips a draft", () => {
    saveDraft(sampleDraft());
    expect(loadDraft()?.draft).toEqual(sampleDraft());
    clearDraft();
    expect(loadDraft()).toBeNull();
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
      expect(() => clearDraft()).not.toThrow();
      expect(loadDraft()).toBeNull();
    } finally {
      if (original) Object.defineProperty(window, "localStorage", original);
    }
  });
});
