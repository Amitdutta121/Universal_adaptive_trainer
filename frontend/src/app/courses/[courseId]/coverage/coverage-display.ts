/**
 * Pure helpers for the coverage grid: column order, cell styling, and the
 * per-topic roll-ups that `TopicCoverage` does not serialise.
 */

import type {
  CoverageState,
  Difficulty,
  QuestionSetOut,
  SubtopicCoverage,
  TopicCoverage,
} from "@/lib/api/types";

/** Fixed column order for the grid, independent of the order the API lists cells. */
export const DIFFICULTY_ORDER: readonly Difficulty[] = ["easy", "medium", "hard"];

export const DIFFICULTY_LABEL: Record<Difficulty, string> = {
  easy: "Easy",
  medium: "Medium",
  hard: "Hard",
};

/** The word shown in each cell, so state is not carried by colour alone. */
export const CELL_STATE_LABEL: Record<CoverageState, string> = {
  empty: "none",
  thin: "thin",
  ready: "ready",
};

export const CELL_STATE_CLASS: Record<CoverageState, string> = {
  empty: "bg-destructive/10 text-destructive border-destructive/30",
  thin: "bg-amber-500/10 text-amber-700 border-amber-500/30 dark:text-amber-400",
  ready: "bg-muted/40 text-muted-foreground border-border",
};

/** This row's cell for one difficulty, or `undefined` if it has none. */
export function cellFor(row: SubtopicCoverage, difficulty: Difficulty) {
  return (row.cells ?? []).find((cell) => cell.difficulty === difficulty);
}

/** Cells in this row still owed questions (`needed > 0`). */
export function rowGapCount(row: SubtopicCoverage): number {
  return (row.cells ?? []).filter((cell) => cell.needed > 0).length;
}

export function rowEmptyCount(row: SubtopicCoverage): number {
  return (row.cells ?? []).filter((cell) => cell.state === "empty").length;
}

export function rowThinCount(row: SubtopicCoverage): number {
  return (row.cells ?? []).filter((cell) => cell.state === "thin").length;
}

export function topicGapCount(topic: TopicCoverage): number {
  return (topic.subtopics ?? []).reduce((total, row) => total + rowGapCount(row), 0);
}

export function topicEmptyCount(topic: TopicCoverage): number {
  return (topic.subtopics ?? []).reduce((total, row) => total + rowEmptyCount(row), 0);
}

export function topicThinCount(topic: TopicCoverage): number {
  return (topic.subtopics ?? []).reduce((total, row) => total + rowThinCount(row), 0);
}

export function topicCellCount(topic: TopicCoverage): number {
  return (topic.subtopics ?? []).reduce((total, row) => total + (row.cells ?? []).length, 0);
}

export function topicIsComplete(topic: TopicCoverage): boolean {
  return topicCellCount(topic) > 0 && topicGapCount(topic) === 0;
}

export function topicReadyCount(topic: TopicCoverage): number {
  return topicCellCount(topic) - topicEmptyCount(topic) - topicThinCount(topic);
}

export type TopicCoverageStatus = "empty" | "thin" | "ready";

export function topicStatus(topic: TopicCoverage): TopicCoverageStatus {
  if (topicEmptyCount(topic) > 0) return "empty";
  if (topicThinCount(topic) > 0) return "thin";
  return "ready";
}

export function topicWorstDifficulty(topic: TopicCoverage): Difficulty | null {
  for (const difficulty of DIFFICULTY_ORDER) {
    const matchingCells = (topic.subtopics ?? []).flatMap((row) =>
      (row.cells ?? []).filter((cell) => cell.difficulty === difficulty),
    );
    if (matchingCells.some((cell) => cell.state === "empty")) return difficulty;
  }
  for (const difficulty of DIFFICULTY_ORDER) {
    const matchingCells = (topic.subtopics ?? []).flatMap((row) =>
      (row.cells ?? []).filter((cell) => cell.difficulty === difficulty),
    );
    if (matchingCells.some((cell) => cell.state === "thin")) return difficulty;
  }
  return null;
}

function difficultyRank(value: Difficulty | null): number {
  if (value === null) return Number.POSITIVE_INFINITY;
  return DIFFICULTY_ORDER.indexOf(value);
}

const TOPIC_STATUS_RANK: Record<TopicCoverageStatus, number> = {
  empty: 0,
  thin: 1,
  ready: 2,
};

export function sortTopicsForReadability(topics: readonly TopicCoverage[]): TopicCoverage[] {
  return [...topics].sort((left, right) => {
    const leftStatus = topicStatus(left);
    const rightStatus = topicStatus(right);
    return (
      TOPIC_STATUS_RANK[leftStatus] - TOPIC_STATUS_RANK[rightStatus] ||
      topicGapCount(right) - topicGapCount(left) ||
      topicEmptyCount(right) - topicEmptyCount(left) ||
      topicThinCount(right) - topicThinCount(left) ||
      difficultyRank(topicWorstDifficulty(left)) - difficultyRank(topicWorstDifficulty(right)) ||
      left.topic_name.localeCompare(right.topic_name)
    );
  });
}

/** A set that lost a member question to deletion: frozen at more than it now holds. */
export function isDamagedSet(
  set: Pick<QuestionSetOut, "member_count" | "question_count">,
): boolean {
  return set.member_count < set.question_count;
}

/** Whether `label` (trimmed, case-insensitive) already names one of `sets`. */
export function labelClashes(
  label: string,
  sets: readonly Pick<QuestionSetOut, "label">[],
): boolean {
  const needle = label.trim().toLowerCase();
  if (!needle) return false;
  return sets.some((set) => set.label.trim().toLowerCase() === needle);
}
