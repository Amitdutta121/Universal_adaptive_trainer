/**
 * The pure logic of the practice flow, kept out of the components so it can be tested directly:
 * the per-topic confidence stub, choosing the next question, and checking answers by running code.
 */

import { runProgram } from "./mini-python";
import type { RunResult } from "./mini-python";
import {
  BANK,
  type ChoiceOption,
  type ChoiceQuestion,
  MISCONCEPTIONS,
  type Misconception,
  type MisconceptionId,
  type ParsonsQuestion,
  type Question,
  TOPICS,
  type TopicId,
} from "./mock-data";

// ---- adaptivity stub ------------------------------------------------------------------------

export type Outcome = "right" | "recovered" | "missed";

export interface TopicStat {
  /** One entry per finished question of the topic: the quiet dots. */
  results: Outcome[];
  /** Wrong answers since the last correct one on this topic. */
  missStreak: number;
  /** 0..1. TODO(real): the real system would use measured mastery, not this two-line heuristic. */
  confidence: number;
}

export type Stats = Record<TopicId, TopicStat>;

/** Two misses on a topic steer the next question to that topic. */
export const STEER_AFTER_MISSES = 2;

const blank = (): TopicStat => ({ results: [], missStreak: 0, confidence: 0.5 });

export function initialStats(): Stats {
  return {
    conditionals: blank(),
    while: blank(),
    functions: blank(),
    lists: blank(),
    recursion: blank(),
  };
}

const clamp = (n: number) => Math.min(1, Math.max(0, Math.round(n * 100) / 100));

/** A wrong attempt (the first or the second on a question). */
export function recordMiss(stats: Stats, topic: TopicId): Stats {
  const old = stats[topic];
  return {
    ...stats,
    [topic]: { ...old, missStreak: old.missStreak + 1, confidence: clamp(old.confidence - 0.25) },
  };
}

/** A correct answer, on the first or the second try. */
export function recordCorrect(stats: Stats, topic: TopicId): Stats {
  const old = stats[topic];
  return { ...stats, [topic]: { ...old, missStreak: 0, confidence: clamp(old.confidence + 0.2) } };
}

/** A question is finished: add its dot. */
export function recordOutcome(stats: Stats, topic: TopicId, outcome: Outcome): Stats {
  const old = stats[topic];
  return { ...stats, [topic]: { ...old, results: [...old.results, outcome] } };
}

export interface NextPick {
  question: Question;
  /** "steered" when a topic with two misses jumped the queue. */
  reason: "order" | "steered";
}

/**
 * The next question: the first unanswered one from a topic with two or more misses (least confident
 * topic first), otherwise the next unanswered one in bank order. Null when the bank is done.
 */
export function pickNext(
  answered: readonly string[],
  stats: Stats,
  bank: readonly Question[] = BANK,
): NextPick | null {
  const open = bank.filter((q) => !answered.includes(q.id));
  const struggling = TOPICS.filter((t) => stats[t.id].missStreak >= STEER_AFTER_MISSES).sort(
    (a, b) => stats[a.id].confidence - stats[b.id].confidence,
  );
  for (const topic of struggling) {
    const question = open.find((q) => q.topic === topic.id);
    if (question) return { question, reason: "steered" };
  }
  return open[0] ? { question: open[0], reason: "order" } : null;
}

// ---- checking answers -----------------------------------------------------------------------

export const isCorrectOption = (option: ChoiceOption) => option.misconception === null;

export function correctOption(question: ChoiceQuestion): ChoiceOption {
  const found = question.options.find(isCorrectOption);
  if (!found) throw new Error(`question ${question.id} has no correct option`);
  return found;
}

/** Does this option describe what `result` really did? Used by the answer-versus-actual panel. */
export function optionMatches(option: ChoiceOption, result: RunResult): boolean {
  if (option.describes === "never_ends") return result.status === "limit";
  if (result.status !== "ok") return false;
  return option.text.trim() === result.output.trim();
}

export const parsonsCode = (question: ParsonsQuestion, order: readonly string[]): string =>
  `${order.map((id) => question.lines.find((l) => l.id === id)?.text ?? "").join("\n")}\n`;

export const parsonsSolution = (question: ParsonsQuestion): string[] =>
  question.lines.map((l) => l.id);

export interface ParsonsCheck {
  correct: boolean;
  result: RunResult;
  /** The tag for a wrong order (mock; TODO(real)). */
  misconception: MisconceptionId | null;
}

/** An order is right when it runs cleanly and prints what the goal says (so equivalent orders pass). */
export function checkParsons(question: ParsonsQuestion, order: readonly string[]): ParsonsCheck {
  const result = runProgram(parsonsCode(question, order));
  const correct = result.status === "ok" && result.output === question.expected;
  if (correct) return { correct, result, misconception: null };
  const misconception = result.status === "ok" ? question.onWrongOutput : question.onError;
  return { correct, result, misconception };
}

export interface FadedCheck {
  passed: boolean;
  /** One short line about why not; empty when passed. */
  feedback: string;
}

/** Runs the worked example's stem plus the student's last line and compares the output. */
export function checkFaded(misconception: Misconception, line: string): FadedCheck {
  const typed = line.trim();
  if (!typed) return { passed: false, feedback: "Type the last line first." };
  const { stem, indent, expected } = misconception.faded;
  const result = runProgram(`${stem}${indent}${typed}\n`);
  if (result.status === "ok" && result.output === expected) return { passed: true, feedback: "" };
  const goal = expected.trim().replace(/\n/g, ", ");
  if (result.status === "ok") {
    const got = result.output.trim().replace(/\n/g, ", ");
    return { passed: false, feedback: `That prints ${got || "nothing"}. The goal is ${goal}.` };
  }
  if (result.status === "limit") {
    return { passed: false, feedback: `That never stops. The goal is ${goal}.` };
  }
  const detail = result.error ? `${result.error.name}: ${result.error.message}` : result.message;
  return { passed: false, feedback: `That does not run (${detail}). The goal is ${goal}.` };
}

export const misconceptionFor = (id: MisconceptionId): Misconception => MISCONCEPTIONS[id];

/** Swap two neighbours, for the move up / move down buttons. */
export function move<T>(items: readonly T[], from: number, to: number): T[] {
  if (to < 0 || to >= items.length || from === to) return [...items];
  const next = [...items];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}
