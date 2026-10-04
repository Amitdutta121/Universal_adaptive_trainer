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
