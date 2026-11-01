import type { Schemas } from "@/lib/api/types";

export type ReviewQueueMode = "all" | "scoreable";
export type ReviewTheme = "signal" | "carbon";
export type ReviewDecision = Schemas["ReviewDecision"];
export type QuestionDetail = Schemas["QuestionDetail"];
export type ReviewOut = Schemas["ReviewOut"];
export type QuestionCheck = Schemas["QuestionCheck"];
export type MetricResult = Schemas["MetricResult"];

export const REVIEW_MODES = ["all", "scoreable"] as const satisfies readonly ReviewQueueMode[];
export const REVIEW_THEMES = ["signal", "carbon"] as const satisfies readonly ReviewTheme[];
export const DECISIONS = ["approve", "reject", "edit"] as const satisfies readonly ReviewDecision[];

export const METRIC_LABEL: Record<string, string> = {
  issues: "Issues",
  subtopic: "Subtopic",
  difficulty: "Difficulty",
  generatability: "Generatability",
};

export type Difficulty = Schemas["Difficulty"];
export type CustomJudgeResult = Schemas["CustomJudgeResult"];
export type GenerationRound = Schemas["GenerationRoundOut"];

export const DIFFICULTIES = ["easy", "medium", "hard"] as const satisfies readonly Difficulty[];
export const DIFFICULTY_LABEL: Record<Difficulty, string> = {
  easy: "Easy",
  medium: "Medium",
  hard: "Hard",
};

/** One taxonomy subtopic a professor can tag a question with, grouped under its topic. */
export type SubtopicOption = { id: number; name: string; topicName: string };

export type RejectionReason = Schemas["RejectionReason"];

/** Mirrors `app/domain/feedback.py::REJECTION_REASON_LABELS`. */
export const REJECTION_REASON_LABEL: Record<RejectionReason, string> = {
  technically_incorrect: "Technically incorrect",
  incorrect_answer: "Incorrect answer",
  incorrect_tests: "Incorrect tests",
  not_grounded_in_source: "Not grounded in source",
  wrong_topic_subtopic: "Wrong topic/subtopic",
  too_easy: "Too easy",
  too_difficult: "Too difficult",
  ambiguous: "Ambiguous",
  poor_wording: "Poor wording",
  poor_distractors: "Poor distractors",
  poor_tests: "Poor tests",
  not_pedagogically_useful: "Not pedagogically useful",
  too_similar_repetitive: "Too similar/repetitive",
  other: "Other",
};

/**
 * The reasons grouped by the judge they count against (`PROFESSOR_OBJECTIONS` in
 * `app/calibration/schema.py`); the last group is held against no judge.
 */
export const REJECTION_REASON_GROUPS: ReadonlyArray<{
  label: string;
  reasons: readonly RejectionReason[];
}> = [
  {
    label: "Issues judge",
    reasons: [
      "technically_incorrect",
      "incorrect_answer",
      "incorrect_tests",
      "not_grounded_in_source",
      "poor_distractors",
      "poor_tests",
      "ambiguous",
      "poor_wording",
      "not_pedagogically_useful",
    ],
  },
  { label: "Subtopic judge", reasons: ["wrong_topic_subtopic"] },
  { label: "Difficulty judge", reasons: ["too_easy", "too_difficult"] },
  { label: "No judge", reasons: ["too_similar_repetitive", "other"] },
];
