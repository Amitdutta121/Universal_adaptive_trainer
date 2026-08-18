import type { Schemas } from "@/lib/api/types";

export type ReviewQueueMode = "all" | "scoreable";
export type ReviewTheme = "signal" | "carbon";
export type ReviewDecision = Schemas["ReviewDecision"];
export type RejectionReason = Schemas["RejectionReason"];
export type QuestionDetail = Schemas["QuestionDetail"];
export type ReviewOut = Schemas["ReviewOut"];
export type QuestionCheck = Schemas["QuestionCheck"];
export type MetricResult = Schemas["MetricResult"];

export const REVIEW_MODES = ["all", "scoreable"] as const satisfies readonly ReviewQueueMode[];
export const REVIEW_THEMES = ["signal", "carbon"] as const satisfies readonly ReviewTheme[];
export const DECISIONS = ["approve", "reject", "edit"] as const satisfies readonly ReviewDecision[];
export const REJECTION_REASONS = [
  "technically_incorrect",
  "incorrect_answer",
  "incorrect_tests",
  "not_grounded_in_source",
  "wrong_topic_subtopic",
  "too_easy",
  "too_difficult",
  "ambiguous",
  "poor_wording",
  "poor_distractors",
  "poor_tests",
  "not_pedagogically_useful",
  "too_similar_repetitive",
  "other",
] as const satisfies readonly RejectionReason[];

export const REASON_LABEL: Record<RejectionReason, string> = {
  technically_incorrect: "Technically incorrect",
  incorrect_answer: "Incorrect answer",
  incorrect_tests: "Incorrect tests",
  not_grounded_in_source: "Not grounded in source",
  wrong_topic_subtopic: "Wrong topic or subtopic",
  too_easy: "Too easy",
  too_difficult: "Too difficult",
  ambiguous: "Ambiguous",
  poor_wording: "Poor wording",
  poor_distractors: "Poor distractors",
  poor_tests: "Poor tests",
  not_pedagogically_useful: "Not pedagogically useful",
  too_similar_repetitive: "Too similar or repetitive",
  other: "Other",
};

export const METRIC_LABEL: Record<string, string> = {
  issues: "Issues",
  subtopic: "Subtopic",
  difficulty: "Difficulty",
  generatability: "Generatability",
};
