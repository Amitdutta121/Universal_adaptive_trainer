import { describe, expect, it } from "vitest";
import {
  copyLabel,
  draftFromVersion,
  draftSignature,
  emptyDraft,
  findProblem,
  toTreeUpdate,
} from "./taxonomy-draft";
import { sampleDraft } from "./taxonomy-draft.fixtures";
import { parseStoredDraft } from "./taxonomy-draft-storage";

const TREE = [
  {
    name: "Loops",
    description: "Repeating actions.",
    subtopics: [
      { name: "for loops", description: null },
      { name: "while loops", description: "Until a condition fails." },
    ],
  },
  {
    name: "Functions",
    description: null,
    subtopics: [{ name: "Defining", description: undefined }],
  },
];

describe("draftFromVersion", () => {
  it("copies names and descriptions in order, turning a missing description into empty text", () => {
    const draft = draftFromVersion("Intro (copy)", TREE);

    expect(draft.label).toBe("Intro (copy)");
    expect(draft.topics.map((t) => t.name)).toEqual(["Loops", "Functions"]);
    expect(draft.topics[0]?.description).toBe("Repeating actions.");
    expect(draft.topics[1]?.description).toBe("");
    expect(draft.topics[0]?.subtopics.map((s) => [s.name, s.description])).toEqual([
      ["for loops", ""],
      ["while loops", "Until a condition fails."],
    ]);
  });

  it("gives every row a fresh, unique id: a draft row is never confused with a saved one", () => {
    const first = draftFromVersion("A", TREE);
    const second = draftFromVersion("A", TREE);
    const ids = (d: typeof first) =>
      d.topics.flatMap((t) => [t.id, ...t.subtopics.map((s) => s.id)]);

    expect(new Set(ids(first)).size).toBe(ids(first).length);
    expect(ids(first).some((id) => ids(second).includes(id))).toBe(false);
  });

  it("produces a draft that passes the same 'finished' check as one typed by hand", () => {
    expect(findProblem(draftFromVersion("Intro (copy)", TREE))).toBeNull();
  });
});

describe("editing a saved taxonomy in place", () => {
  const SAVED = [
    {
      id: 10,
      name: "Loops",
      description: null,
      subtopics: [
        { id: 11, name: "for loops", description: null },
        { id: 12, name: "while loops", description: "Until a condition fails." },
      ],
    },
  ];

  it("remembers which saved row each draft row came from, apart from its own key", () => {
    const draft = draftFromVersion("Intro", SAVED);

    expect(draft.topics[0]?.serverId).toBe(10);
    expect(draft.topics[0]?.subtopics.map((s) => s.serverId)).toEqual([11, 12]);
    expect(draft.topics[0]?.id).not.toBe("10");
  });

  it("leaves rows of a hand-built draft without a saved id", () => {
    expect(sampleDraft().topics.every((t) => t.serverId === undefined)).toBe(true);
    expect(draftFromVersion("A", TREE).topics[0]?.serverId).toBeUndefined();
  });

  it("describes the whole tree for the server: saved ids kept, new rows without one, text trimmed", () => {
    const draft = draftFromVersion("  Intro  ", SAVED);
    draft.topics[0]?.subtopics.push({ id: "new-sub", name: " ranges ", description: "" });
    draft.topics.push({ id: "new-topic", name: "Functions", description: "", subtopics: [] });

    expect(toTreeUpdate(draft)).toEqual({
      label: "Intro",
      topics: [
        {
          id: 10,
          name: "Loops",
          description: "",
          subtopics: [
            { id: 11, name: "for loops", description: "" },
            { id: 12, name: "while loops", description: "Until a condition fails." },
            { id: null, name: "ranges", description: "" },
          ],
        },
        { id: null, name: "Functions", description: "", subtopics: [] },
      ],
    });
  });

  it("changes the draft's signature when a saved row is only renamed", () => {
    const before = draftFromVersion("Intro", SAVED);
    const after = structuredClone(before);
    (after.topics[0] as { name: string }).name = "Iteration";

    expect(draftSignature(after)).not.toBe(draftSignature(before));
  });

  it("keeps saved ids through storage, and refuses a stored id that is not a number", () => {
    const draft = draftFromVersion("Intro", SAVED);
    const stored = (d: unknown) =>
      parseStoredDraft(JSON.stringify({ savedAt: "2026-01-01T00:00:00Z", draft: d, origin: null }));

    expect(stored(draft)?.draft.topics[0]?.serverId).toBe(10);
    const tampered = structuredClone(draft) as unknown as { topics: { serverId: unknown }[] };
    for (const topic of tampered.topics) topic.serverId = "10; drop";
    expect(stored(tampered)).toBeNull();
  });
});

describe("copyLabel", () => {
  it("adds (copy) once, however many times a copy is copied", () => {
    expect(copyLabel("Intro")).toBe("Intro (copy)");
    expect(copyLabel("Intro (copy)")).toBe("Intro (copy)");
    expect(copyLabel("Intro (Copy)  ")).toBe("Intro (Copy)  ");
  });
});

describe("draftSignature", () => {
  it("is unchanged by editing something and editing it back, and changed by any real edit", () => {
    const draft = draftFromVersion("X", TREE);
    const before = draftSignature(draft);

    const edited = structuredClone(draft);
    (edited.topics[0] as { name: string }).name = "Loops!";
    expect(draftSignature(edited)).not.toBe(before);

    (edited.topics[0] as { name: string }).name = "Loops";
    expect(draftSignature(edited)).toBe(before);
  });

  it("treats a blank draft as the baseline for a new taxonomy", () => {
    expect(draftSignature(emptyDraft())).toBe(draftSignature({ label: "", topics: [] }));
    expect(draftSignature({ label: "typed", topics: [] })).not.toBe(draftSignature(emptyDraft()));
  });
});

describe("stored drafts and where they came from", () => {
  const stored = (extra: object) =>
    JSON.stringify({ savedAt: "2026-01-01T00:00:00Z", draft: sampleDraft(), ...extra });

  it("keeps the origin a draft was opened from", () => {
    expect(parseStoredDraft(stored({ origin: { id: 3, label: "Intro" } }))?.origin).toEqual({
      id: 3,
      label: "Intro",
    });
  });

  it("reads a draft saved before origins existed, or with a malformed origin, as having none", () => {
    expect(parseStoredDraft(stored({}))?.origin).toBeNull();
    expect(parseStoredDraft(stored({ origin: { id: "3", label: "Intro" } }))?.origin).toBeNull();
    expect(parseStoredDraft(stored({ origin: "Intro" }))?.origin).toBeNull();
    // A bad origin does not throw away the work itself.
    expect(parseStoredDraft(stored({ origin: 7 }))?.draft.label).toBe("Introductory Python");
  });
});
