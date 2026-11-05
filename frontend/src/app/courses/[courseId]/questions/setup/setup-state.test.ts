import { describe, expect, it } from "vitest";
import type { QuestionSetup } from "@/lib/api/types";
import {
  COURSE,
  effectiveStyleIds,
  initialLayers,
  isCustom,
  liveCourseOn,
  resetSubtopic,
  type SetupContext,
  type SetupSubtopic,
  type SetupTopic,
  saveRequest,
  setStyles,
  subtopicsWithoutStyle,
} from "./setup-state";

const LIBRARY = [
  { id: "trace", question_type: "output_prediction" },
  { id: "fill", question_type: "code_completion" },
  { id: "debug", question_type: "debugging" },
  { id: "concept", question_type: "multiple_choice" },
  { id: "write", question_type: "coding" },
];

/** `coding` is in the library but not allowed in the course. */
const CONTEXT: SetupContext = {
  library: LIBRARY,
  allowed: new Set(["output_prediction", "code_completion", "debugging", "multiple_choice"]),
};

const subtopic = (id: number, styleIds: string[] | null): SetupSubtopic => ({
  id,
  name: `Subtopic ${id}`,
  suggestion: styleIds ? { subtopic_id: id, style_ids: styleIds, reason: "" } : null,
});

const LOOPS = subtopic(11, ["trace", "fill"]);
const STRINGS = subtopic(12, ["fill", "write"]);
const NONE = subtopic(13, null);
const TOPICS: SetupTopic[] = [{ id: 1, name: "Topic", subtopics: [LOOPS, STRINGS, NONE] }];

const saved = (approved: Record<number, string[]>): QuestionSetup => ({
  id: 1,
  curriculum_version_id: 3,
  approved_styles: Object.entries(approved).map(([id, style_ids]) => ({
    subtopic_id: Number(id),
    style_ids,
  })),
  cell_targets: [],
  created_at: "2026-11-01T10:00:00Z",
  latest_round: null,
});

/** `TOPICS` as `setupTopics` builds them when editing: no suggestion, the saved styles. */
const editTopics = (current: QuestionSetup): SetupTopic[] => {
  const byId = new Map(current.approved_styles.map((entry) => [entry.subtopic_id, entry.style_ids]));
  return TOPICS.map((topic) => ({
    ...topic,
    subtopics: topic.subtopics.map((entry) => ({
      ...entry,
      suggestion: null,
      saved: byId.get(entry.id) ?? [],
    })),
  }));
};

describe("initialLayers", () => {
  it("starts a new setup with every style of an allowed type on and nothing local", () => {
    const layers = initialLayers(CONTEXT, null);
    expect([...layers.courseOn]).toEqual(["trace", "fill", "debug", "concept"]);
    expect(layers.overrides).toEqual({});
    expect(effectiveStyleIds(layers, CONTEXT, LOOPS)).toEqual(["trace", "fill"]);
    // A suggested style of a blocked type is not used.
    expect(effectiveStyleIds(layers, CONTEXT, STRINGS)).toEqual(["fill"]);
    expect(effectiveStyleIds(layers, CONTEXT, NONE)).toEqual([]);
  });

  it("starts an edit from what was saved: nothing local, saved back unchanged", () => {
    const current = saved({ 11: ["trace", "debug"], 12: ["fill"], 13: ["concept"] });
    const topics = editTopics(current);
    const layers = initialLayers(CONTEXT, current);

    expect([...layers.courseOn].sort()).toEqual(["concept", "debug", "fill", "trace"]);
    // Each subtopic's saved styles are its fit, so nothing reads as a local edit.
    expect(layers.overrides).toEqual({});
    expect(effectiveStyleIds(layers, CONTEXT, topics[0].subtopics[0])).toEqual(["trace", "debug"]);

    const body = saveRequest(3, layers, CONTEXT, topics, current.cell_targets);
    expect(body.approved_styles).toEqual(current.approved_styles);
  });

  it("when editing, course switches reach every subtopic", () => {
    const current = saved({ 11: ["trace"], 12: ["fill"] });
    const topics = editTopics(current);
    const [loops, strings] = topics[0].subtopics;
    const start = initialLayers(CONTEXT, current);

    // A style no subtopic had, turned on for the course, reaches them all.
    const withConcept = setStyles(start, CONTEXT, COURSE, ["concept"], true);
    expect(effectiveStyleIds(withConcept, CONTEXT, loops)).toEqual(["trace", "concept"]);
    expect(effectiveStyleIds(withConcept, CONTEXT, strings)).toEqual(["fill", "concept"]);
    // Turning a saved style off for the course takes it from the subtopic that had it.
    const withoutFill = setStyles(start, CONTEXT, COURSE, ["fill"], false);
    expect(effectiveStyleIds(withoutFill, CONTEXT, strings)).toEqual([]);
    // Back on, it returns only where it was saved.
    const fillAgain = setStyles(withoutFill, CONTEXT, COURSE, ["fill"], true);
    expect(effectiveStyleIds(fillAgain, CONTEXT, strings)).toEqual(["fill"]);
    expect(effectiveStyleIds(fillAgain, CONTEXT, loops)).toEqual(["trace"]);
    // A subtopic edit is local and Custom, and resets to what was saved.
    const local = setStyles(start, CONTEXT, loops, ["trace"], false);
    expect(isCustom(local, 11)).toBe(true);
    expect(effectiveStyleIds(resetSubtopic(local, 11), CONTEXT, loops)).toEqual(["trace"]);
  });

  it("leaves a course style no subtopic used off", () => {
    const layers = initialLayers(CONTEXT, saved({ 11: ["trace"], 12: ["fill"] }));
    expect(liveCourseOn(layers, CONTEXT).has("debug")).toBe(false);
  });
});

describe("setStyles", () => {
  const start = initialLayers(CONTEXT, null);

  it("turns a style off for the course and so for every subtopic", () => {
    const layers = setStyles(start, CONTEXT, COURSE, ["fill"], false);
    expect(effectiveStyleIds(layers, CONTEXT, LOOPS)).toEqual(["trace"]);
    expect(effectiveStyleIds(layers, CONTEXT, STRINGS)).toEqual([]);
    expect(isCustom(layers, LOOPS.id)).toBe(false);
    expect(subtopicsWithoutStyle(layers, CONTEXT, TOPICS).map((s) => s.id)).toEqual([12, 13]);

    const back = setStyles(layers, CONTEXT, COURSE, ["fill"], true);
    expect(effectiveStyleIds(back, CONTEXT, STRINGS)).toEqual(["fill"]);
  });

  it("keeps a subtopic edit local and resets it", () => {
    let layers = setStyles(start, CONTEXT, LOOPS, ["fill"], false);
    layers = setStyles(layers, CONTEXT, LOOPS, ["debug"], true);
    expect(effectiveStyleIds(layers, CONTEXT, LOOPS)).toEqual(["trace", "debug"]);
    expect(effectiveStyleIds(layers, CONTEXT, STRINGS)).toEqual(["fill"]);
    expect(isCustom(layers, LOOPS.id)).toBe(true);

    expect(isCustom(resetSubtopic(layers, LOOPS.id), LOOPS.id)).toBe(false);
    expect(effectiveStyleIds(resetSubtopic(layers, LOOPS.id), CONTEXT, LOOPS)).toEqual([
      "trace",
      "fill",
    ]);
  });

  it("drops an override that undoes itself", () => {
    const off = setStyles(start, CONTEXT, LOOPS, ["fill"], false);
    expect(isCustom(setStyles(off, CONTEXT, LOOPS, ["fill"], true), LOOPS.id)).toBe(false);
    const added = setStyles(start, CONTEXT, LOOPS, ["debug"], true);
    expect(isCustom(setStyles(added, CONTEXT, LOOPS, ["debug"], false), LOOPS.id)).toBe(false);
  });

  it("lets a subtopic use only styles the course has on", () => {
    const courseOff = setStyles(start, CONTEXT, COURSE, ["debug"], false);
    const layers = setStyles(courseOff, CONTEXT, LOOPS, ["debug", "write"], true);
    expect(effectiveStyleIds(layers, CONTEXT, LOOPS)).toEqual(["trace", "fill"]);
    expect(isCustom(layers, LOOPS.id)).toBe(false);
  });

  it("turns a whole type on or off at once", () => {
    const ids = LIBRARY.filter((s) => s.question_type === "code_completion").map((s) => s.id);
    const off = setStyles(start, CONTEXT, COURSE, ids, false);
    expect(liveCourseOn(off, CONTEXT).has("fill")).toBe(false);
    expect(liveCourseOn(setStyles(off, CONTEXT, COURSE, ids, true), CONTEXT).has("fill")).toBe(
      true,
    );
  });
});

describe("allowed types", () => {
  it("remembers a blocked type's styles and brings them back when it is allowed", () => {
    const withWrite = initialLayers(CONTEXT, saved({ 11: ["trace"], 12: ["write"] }));
    expect(withWrite.courseOn.has("write")).toBe(true);
    expect(effectiveStyleIds(withWrite, CONTEXT, STRINGS)).toEqual([]);

    const allowed: SetupContext = {
      ...CONTEXT,
      allowed: new Set([...CONTEXT.allowed, "coding"]),
    };
    expect(effectiveStyleIds(withWrite, allowed, STRINGS)).toEqual(["write"]);
  });

  it("never saves a style of a blocked type", () => {
    const layers = setStyles(
      initialLayers(CONTEXT, null),
      CONTEXT,
      COURSE,
      ["write"],
      true,
    );
    const body = saveRequest(3, layers, CONTEXT, TOPICS, []);
    expect(body.approved_styles.flatMap((entry) => entry.style_ids)).not.toContain("write");
  });
});
