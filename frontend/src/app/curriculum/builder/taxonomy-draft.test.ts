import { describe, expect, it } from "vitest";
import {
  countMatches,
  countSubtopics,
  describeRemoval,
  emptyDraft,
  filterTree,
  findProblem,
  isDraftEmpty,
  limitsFromGuide,
  moveSubtopic,
  moveTopic,
  removeSubtopic,
  removeTopic,
  restoreRemoval,
  toTaxonomyDocument,
} from "./taxonomy-draft";
import { sampleDraft } from "./taxonomy-draft.fixtures";

const names = (draft: ReturnType<typeof sampleDraft>) => draft.topics.map((topic) => topic.name);

describe("filterTree", () => {
  const { topics } = sampleDraft();

  it("shows everything for a blank search", () => {
    expect(filterTree(topics, "  ")).toHaveLength(topics.length);
  });

  it("keeps every subtopic of a topic that matches on its own", () => {
    // "Loops" matches by name, so both its subtopics stay for context.
    const [loops] = filterTree(topics, "loops");
    expect(loops?.topic.name).toBe("Loops");
    expect(loops?.subtopics).toHaveLength(2);
  });

  it("lists only the matching subtopics when the topic itself does not match", () => {
    const shown = filterTree(topics, "rebinding");
    expect(shown.map((row) => row.topic.name)).toEqual(["Variables"]);
    expect(shown[0]?.subtopics.map((s) => s.name)).toEqual(["Assignment and rebinding"]);
  });

  it("searches descriptions as well as names, case-insensitively", () => {
    expect(filterTree(topics, "INT, FLOAT")[0]?.subtopics.map((s) => s.name)).toEqual([
      "Basic types",
    ]);
  });

  it("counts only items that matched themselves, not rows shown for context", () => {
    // "while" matches the Loops description and the "while loops" subtopic, but not "for loops…".
    expect(countMatches(topics, "while")).toBe(2);
    expect(countMatches(topics, "")).toBe(0);
  });
});

describe("removal and undo", () => {
  it("puts a removed topic back at its original position, subtopics included", () => {
    const start = sampleDraft();
    const { draft, removal } = removeTopic(start, "topic-b");
    expect(names(draft)).toEqual(["Variables", "Functions", "Files"]);
    expect(describeRemoval(removal)).toBe("Removed topic “Loops” and its 2 subtopics");
    expect(restoreRemoval(draft, removal)).toEqual(start);
  });

  it("puts a removed subtopic back at its original position", () => {
    const start = sampleDraft();
    const { draft, removal } = removeSubtopic(start, "topic-a", "sub-a2");
    expect(countSubtopics(draft)).toBe(countSubtopics(start) - 1);
    expect(restoreRemoval(draft, removal)).toEqual(start);
  });

  it("undoes several removals in reverse order back to the start", () => {
    const start = sampleDraft();
    const first = removeSubtopic(start, "topic-a", "sub-a1");
    const second = removeTopic(first.draft, "topic-a");
    const back = restoreRemoval(restoreRemoval(second.draft, second.removal), first.removal);
    expect(back).toEqual(start);
  });

  it("clamps the position when the list has shrunk since the removal", () => {
    const start = sampleDraft();
    const first = removeTopic(start, "topic-d");
    const second = removeTopic(first.draft, "topic-c");
    const restored = restoreRemoval(second.draft, first.removal);
    expect(names(restored)).toEqual(["Variables", "Loops", "Files"]);
  });

  it("throws for an id that is not there rather than silently removing nothing", () => {
    expect(() => removeTopic(sampleDraft(), "nope")).toThrow();
    expect(() => removeSubtopic(sampleDraft(), "topic-a", "nope")).toThrow();
  });
});

describe("reordering", () => {
  it("moves a topic and ignores a move off either end", () => {
    const start = sampleDraft();
    expect(names(moveTopic(start, "topic-a", 1)).slice(0, 2)).toEqual(["Loops", "Variables"]);
    expect(names(moveTopic(start, "topic-a", -1))).toEqual(names(start));
    expect(names(moveTopic(start, "topic-d", 1))).toEqual(names(start));
  });

  it("moves a subtopic within its own topic only", () => {
    const moved = moveSubtopic(sampleDraft(), "topic-a", "sub-a1", 1);
    expect(moved.topics[0]?.subtopics.map((s) => s.id)).toEqual(["sub-a2", "sub-a1", "sub-a3"]);
    expect(moved.topics[1]).toEqual(sampleDraft().topics[1]);
  });
});

describe("toTaxonomyDocument", () => {
  it("emits the backend's document shape, trimmed, with the schema version it was given", () => {
    const draft = sampleDraft();
    draft.label = "  Intro  ";
    const [first] = draft.topics;
    if (first) first.name = " Variables ";

    const document = toTaxonomyDocument(draft, "7");
    expect(document.schema_version).toBe("7");
    expect(document.label).toBe("Intro");
    expect(document.topics[0]?.name).toBe("Variables");
    // No ids, no UI state: the backend forbids extra keys.
    expect(Object.keys(document)).toEqual(["schema_version", "label", "topics"]);
    expect(Object.keys(document.topics[0] ?? {})).toEqual(["name", "description", "subtopics"]);
    expect(Object.keys(document.topics[0]?.subtopics[0] ?? {})).toEqual(["name", "description"]);
  });

  it("sends a blank description as an empty string, which is what the schema defaults it to", () => {
    expect(toTaxonomyDocument(sampleDraft(), "1").topics[0]?.subtopics[2]?.description).toBe("");
  });
});

describe("findProblem", () => {
  const finished = () => {
    const draft = sampleDraft();
    draft.topics = draft.topics.filter((topic) => topic.subtopics.length > 0);
    return draft;
  };

  it("passes a finished draft, leaving every other rule to the backend", () => {
    expect(findProblem(finished())).toBeNull();
    // A duplicate name is not this function's business: the backend refuses it and says why.
    const duplicate = finished();
    duplicate.topics[1]?.subtopics.push({ id: "dup", name: "while loops", description: "" });
    expect(findProblem(duplicate)).toBeNull();
  });

  it("asks for a label and for a topic first", () => {
    expect(findProblem(emptyDraft())?.at).toBe("label");
    expect(findProblem({ ...finished(), label: " " })?.message).toMatch(/name/i);
    expect(findProblem({ label: "x", topics: [] })?.message).toMatch(/topic/i);
  });

  it("points at the topic that has no subtopics", () => {
    const problem = findProblem(sampleDraft());
    expect(problem?.at).toEqual({ topicId: "topic-d", subtopicId: null });
    expect(problem?.message).toContain("Files");
  });

  it("points at a blank subtopic name, and at a blank topic name before that", () => {
    const draft = finished();
    const sub = draft.topics[0]?.subtopics[1];
    if (sub) sub.name = "  ";
    expect(findProblem(draft)?.at).toEqual({ topicId: "topic-a", subtopicId: "sub-a2" });

    const first = draft.topics[0];
    if (first) first.name = "";
    expect(findProblem(draft)?.at).toEqual({ topicId: "topic-a", subtopicId: null });
  });
});

describe("limitsFromGuide", () => {
  const fields = [
    { path: "label", max_length: 200 },
    { path: "topics[].name", max_length: 300 },
    { path: "topics[].description", max_length: 2000 },
    { path: "topics[].subtopics[].name", max_length: 310 },
    { path: "topics[].subtopics[].description", max_length: 2100 },
    { path: "topics", max_length: null },
  ];

  it("reads each bound from the path it applies to", () => {
    expect(limitsFromGuide(fields)).toEqual({
      label: 200,
      topicName: 300,
      topicDescription: 2000,
      subtopicName: 310,
      subtopicDescription: 2100,
    });
  });

  it("has no limits until the guide has loaded, rather than a hard-coded guess", () => {
    expect(limitsFromGuide(undefined)).toEqual({});
  });
});

describe("isDraftEmpty", () => {
  it("is empty only with no label and no topics", () => {
    expect(isDraftEmpty(emptyDraft())).toBe(true);
    expect(isDraftEmpty({ label: "x", topics: [] })).toBe(false);
    expect(isDraftEmpty(sampleDraft())).toBe(false);
  });
});
