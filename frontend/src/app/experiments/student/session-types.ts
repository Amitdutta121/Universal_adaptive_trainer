/**
 * The in-memory session state for the student-experience prototype. In the real
 * app this is spread across a training session, a per-student progress record
 * and the served-question endpoint; here it is one plain object, persisted to
 * localStorage so a reload resumes where you were.
 */

import type { Progress, ScoreLabel, ScoreResult, SelectionResult } from "./mock-data";

export type Phase = "welcome" | "loading" | "question" | "result" | "summary";

export type Attempt = {
  ordinal: number;
  questionId: string;
  questionPrompt: string;
  topicName: string;
  subtopicName: string;
  answer: string;
  score: number;
  label: ScoreLabel;
};

export type LastResult = ScoreResult & {
  questionId: string;
  answer: string;
  topicName: string;
  topicBefore: number;
  topicAfter: number;
};

export type SessionState = {
  phase: Phase;
  setId: string | null;
  learnerName: string;
  seed: number;
  /** Bumped every time a question is served — drives the seeded selection. */
  step: number;
  answeredIds: string[];
  attempts: Attempt[];
  progress: Progress | null;
  current: SelectionResult | null;
  lastResult: LastResult | null;
  /** A polite screen-reader announcement for the most recent state change. */
  announcement: string;
};

export const EMPTY_SESSION: SessionState = {
  phase: "welcome",
  setId: null,
  learnerName: "",
  seed: 1,
  step: 0,
  answeredIds: [],
  attempts: [],
  progress: null,
  current: null,
  lastResult: null,
  announcement: "",
};

export const SESSION_STORAGE_KEY = "adaptive-trainer:experiment:student";
export const NAME_STORAGE_KEY = "adaptive-trainer:experiment:student-name";
