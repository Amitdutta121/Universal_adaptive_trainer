import { describe, expect, it } from "vitest";
import type { AttemptOut } from "@/lib/api/types";
import { buildScoreTrend } from "./score-trend";

function attempt(overrides: Partial<AttemptOut>): AttemptOut {
  return {
    id: 1,
    session_id: 2,
    ordinal: 1,
    question_id: 11,
    question_type: "multiple_choice",
    subtopic_id: 5,
    requested_difficulty: "easy",
    served_difficulty: "easy",
    score: 100,
    passed_tests: null,
    total_tests: null,
    answer: null,
    created_at: "2026-08-20T10:00:00Z",
    answered_at: "2026-08-20T10:01:00Z",
    ...overrides,
  };
}

describe("buildScoreTrend", () => {
  it("keeps only scored attempts and orders them oldest to newest", () => {
    const points = buildScoreTrend([
      attempt({ id: 2, ordinal: 3, score: 40, answered_at: "2026-08-22T10:00:00Z" }),
      attempt({ id: 3, ordinal: 2, score: null, answered_at: null }),
      attempt({ id: 1, ordinal: 1, score: 90, answered_at: "2026-08-21T10:00:00Z" }),
    ]);

    expect(points.map((point) => point.attemptId)).toEqual([1, 2]);
    expect(points.map((point) => point.score)).toEqual([90, 40]);
    expect(points.map((point) => point.averageScore)).toEqual([90, 65]);
  });

  it("turns question type codes into readable labels", () => {
    const points = buildScoreTrend([
      attempt({ question_type: "coding" }),
      attempt({ id: 2, question_type: null, answered_at: "2026-08-21T10:00:00Z" }),
    ]);

    expect(points[0]?.questionType).toBe("coding");
    expect(points[1]?.questionType).toBe("question");
  });
});
