import { describe, expect, it } from "vitest";
import {
  type Answer,
  byDifficulty,
  byDifficultyAndAnswer,
  byDifficultyOverTime,
  bySubtopicsExplored,
  firstVsLatest,
  learningCurve,
  rateOf,
} from "./learning-analysis";
import { MOCK_CLASS, updateMastery } from "./mock-learning";

const a = (student: string, subtopic: string, correct: boolean): Answer => ({
  student,
  subtopic,
  difficulty: "easy",
  correct,
});

describe("rateOf", () => {
  it("gives the share with a Wilson interval, and flags thin counts", () => {
    const thin = rateOf(2, 4);
    expect(thin.rate).toBe(50);
    expect(thin.enough).toBe(false);
    const wide = rateOf(50, 100);
    expect(wide.low).toBeCloseTo(40.4, 0);
    expect(wide.high).toBeCloseTo(59.6, 0);
    expect(wide.enough).toBe(true);
    expect(rateOf(0, 0).rate).toBeNull();
  });
});

describe("learningCurve", () => {
  // s1 is moved on after one right answer; s2 struggles for three.
  const answers = [
    a("s1", "loops", true),
    a("s2", "loops", false),
    a("s2", "loops", false),
    a("s2", "loops", true),
  ];

  it("everyone: later points are only the students still there", () => {
    const { everyone } = learningCurve(answers, 3);
    expect(everyone.map((point) => [point.n, point.rate])).toEqual([
      [2, 50],
      [1, 0],
      [1, 100],
    ]);
  });

  it("cohort: the same sequences at every point", () => {
    const { cohort, cohortSize } = learningCurve(answers, 3);
    expect(cohortSize).toBe(1);
    expect(cohort.map((point) => point.n)).toEqual([1, 1, 1]);
  });
});

describe("bySubtopicsExplored", () => {
  it("counts each answer at the student's number of subtopics reached so far", () => {
    const points = bySubtopicsExplored([
      a("s1", "loops", false),
      a("s1", "loops", true),
      a("s1", "lists", true),
      // Back on loops after reaching lists: still two subtopics explored.
      a("s1", "loops", true),
      a("s2", "loops", true),
    ]);
    expect(points.map((point) => [point.explored, point.n, point.correct, point.students])).toEqual(
      [
        [1, 3, 2, 2],
        [2, 2, 2, 1],
      ],
    );
  });
});

describe("byDifficulty", () => {
  it("scores each served difficulty, keeping empty levels as no answers", () => {
    const hard = (correct: boolean): Answer => ({ ...a("s2", "loops", correct), difficulty: "hard" });
    const rows = byDifficulty([a("s1", "loops", true), a("s1", "loops", false), hard(false)]);
    expect(rows.map((row) => [row.difficulty, row.n, row.correct, row.students])).toEqual([
      ["easy", 2, 1, 1],
      ["medium", 0, 0, 0],
      ["hard", 1, 0, 1],
    ]);
    expect(rows[1].rate).toBeNull();
  });
});

describe("byDifficultyOverTime", () => {
  const at = (answer: Answer, iso: string): Answer => ({ ...answer, at: iso });

  it("buckets by day over a short span, keeping empty days", () => {
    const rows = byDifficultyOverTime([
      at(a("s1", "loops", true), "2026-10-16T18:00:00Z"),
      at({ ...a("s1", "loops", false), difficulty: "hard" }, "2026-10-18T09:00:00Z"),
      a("s2", "loops", true), // no time: left out
    ]);
    expect(rows.map((row) => [row.start, row.unit, row.total, row.easy.n, row.hard.n])).toEqual([
      ["2026-10-16", "day", 1, 1, 0],
      ["2026-10-17", "day", 0, 0, 0],
      ["2026-10-18", "day", 1, 0, 1],
    ]);
  });

  it("switches to Monday weeks past three weeks", () => {
    const rows = byDifficultyOverTime([
      at(a("s1", "loops", true), "2026-09-09T10:00:00Z"), // a Wednesday
      at(a("s1", "loops", true), "2026-10-14T10:00:00Z"),
    ]);
    expect(rows[0]).toMatchObject({ start: "2026-09-07", unit: "week" });
    expect(rows).toHaveLength(6);
  });
});

describe("firstVsLatest", () => {
  it("pairs a student's first and latest answer on a subtopic", () => {
    const [all] = firstVsLatest([
      a("s1", "loops", false),
      a("s1", "loops", true),
      a("s2", "loops", true),
      a("s2", "loops", false),
      a("s3", "loops", true),
    ]);
    expect([all.improved, all.same, all.worse]).toEqual([1, 0, 1]);
    expect(all.first.n).toBe(2);
  });
});

describe("byDifficultyAndAnswer", () => {
  it("buckets by answer number on each subtopic, starting over on a new one", () => {
    const rows = byDifficultyAndAnswer(
      [
        a("s1", "loops", false),
        a("s1", "loops", true),
        a("s1", "loops", true),
        a("s1", "lists", false),
      ],
      2,
    );
    expect(rows.map((row) => [row.label, row.easy.n, row.easy.correct])).toEqual([
      ["1", 2, 0],
      ["2+", 2, 2],
    ]);
  });
});

describe("the simulated class", () => {
  it("learns: the fixed cohort ends higher than it starts", () => {
    const { cohort } = learningCurve(MOCK_CLASS, 4);
    expect(cohort[3].rate ?? 0).toBeGreaterThan((cohort[0].rate ?? 0) + 15);
  });
});

describe("the simulated class moves on like the tutor", () => {
  it("updates mastery with the engine's BKT step", () => {
    // Same numbers as app.adaptive.state.update_mastery(0.1, 100 / 0) with default parameters.
    expect(updateMastery(0.1, true)).toBeCloseTo(0.28247, 4);
    expect(updateMastery(0.1, false)).toBeCloseTo(0.03764, 4);
  });

  it("leaves a subtopic once mastery reaches 0.60, not after a streak", () => {
    const runs = new Map<string, boolean[]>();
    for (const answer of MOCK_CLASS) {
      const key = `${answer.student}|${answer.subtopic}`;
      runs.set(key, [...(runs.get(key) ?? []), answer.correct]);
    }
    for (const run of runs.values()) {
      let mastery = 0.1;
      for (const correct of run) {
        // Every answer was asked while mastery was still under the ceiling.
        expect(mastery).toBeLessThan(0.6);
        mastery = updateMastery(mastery, correct);
      }
      expect(mastery >= 0.6 || run.length === 9).toBe(true);
    }
  });
});
