/**
 * Pins the grid's wording and roll-ups: every cell state has a label and a
 * class, the columns keep one order whatever order the API sends, and a topic
 * counts as complete only when it has cells and no gaps.
 */

import { describe, expect, it } from "vitest";
import type { CoverageState, SubtopicCoverage, TopicCoverage } from "@/lib/api/types";
import {
  CELL_STATE_CLASS,
  CELL_STATE_LABEL,
  cellFor,
  DIFFICULTY_ORDER,
  isDamagedSet,
  labelClashes,
  rowGapCount,
  topicGapCount,
  topicIsComplete,
} from "./coverage-display";

const STATES: CoverageState[] = ["empty", "thin", "ready"];

function row(overrides: Partial<SubtopicCoverage> = {}): SubtopicCoverage {
  return {
    subtopic_id: 1,
    subtopic_name: "Subtopic",
    topic_id: 1,
    topic_name: "Topic",
    cells: [
      { difficulty: "easy", count: 3, state: "ready", needed: 0 },
      { difficulty: "medium", count: 1, state: "thin", needed: 2 },
      { difficulty: "hard", count: 0, state: "empty", needed: 3 },
    ],
    ...overrides,
  };
}

describe("cell state maps", () => {
  it("covers every state the backend can send", () => {
    for (const map of [CELL_STATE_LABEL, CELL_STATE_CLASS]) {
      expect(Object.keys(map).sort()).toEqual([...STATES].sort());
    }
  });

  it("gives every state a non-empty word", () => {
    for (const state of STATES) {
      expect(CELL_STATE_LABEL[state]).toBeTruthy();
    }
  });

  it("reserves the destructive treatment for an empty cell", () => {
    expect(CELL_STATE_CLASS.empty).toMatch(/destructive/);
    expect(CELL_STATE_CLASS.thin).not.toMatch(/destructive/);
    expect(CELL_STATE_CLASS.ready).not.toMatch(/destructive/);
  });
});

describe("cellFor", () => {
  it("picks the cell for one difficulty, or undefined", () => {
    expect(cellFor(row(), "medium")?.count).toBe(1);
    expect(cellFor(row({ cells: [] }), "easy")).toBeUndefined();
  });

  it("matches the pinned column order", () => {
    expect(DIFFICULTY_ORDER).toEqual(["easy", "medium", "hard"]);
  });
});

describe("roll-ups", () => {
  it("counts a row's cells still owed questions", () => {
    expect(rowGapCount(row())).toBe(2);
    expect(rowGapCount(row({ cells: [] }))).toBe(0);
  });

  it("sums gaps across a topic's rows", () => {
    const topic: TopicCoverage = {
      topic_id: 1,
      topic_name: "Topic",
      approved_questions: 4,
      subtopics: [row(), row()],
    };
    expect(topicGapCount(topic)).toBe(4);
    expect(topicIsComplete(topic)).toBe(false);
  });

  it("calls a topic complete only when it has cells and no gaps", () => {
    const done: TopicCoverage = {
      topic_id: 1,
      topic_name: "Topic",
      approved_questions: 9,
      subtopics: [
        row({
          cells: [
            { difficulty: "easy", count: 3, state: "ready", needed: 0 },
            { difficulty: "medium", count: 5, state: "ready", needed: 0 },
            { difficulty: "hard", count: 3, state: "ready", needed: 0 },
          ],
        }),
      ],
    };
    expect(topicIsComplete(done)).toBe(true);

    const noCells: TopicCoverage = {
      topic_id: 2,
      topic_name: "Empty",
      approved_questions: 0,
      subtopics: [],
    };
    expect(topicIsComplete(noCells)).toBe(false);
  });
});

describe("frozen set helpers", () => {
  it("flags a set holding fewer members than it froze", () => {
    expect(isDamagedSet({ member_count: 9, question_count: 10 })).toBe(true);
    expect(isDamagedSet({ member_count: 10, question_count: 10 })).toBe(false);
  });

  it("matches an existing label case- and space-insensitively", () => {
    const sets = [{ label: "Midterm one" }];
    expect(labelClashes("  midterm ONE ", sets)).toBe(true);
    expect(labelClashes("Final", sets)).toBe(false);
    expect(labelClashes("   ", sets)).toBe(false);
  });
});
