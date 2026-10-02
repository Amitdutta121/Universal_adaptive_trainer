import type { AttemptOut } from "@/lib/api/types";

export interface ScoreTrendPoint {
  averageScore: number;
  attemptId: number;
  label: string;
  ordinal: number;
  questionType: string;
  score: number;
  timestamp: string;
}

function shortLabel(iso: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
  }).format(new Date(iso));
}

function questionTypeLabel(questionType: AttemptOut["question_type"]) {
  return questionType ? questionType.replaceAll("_", " ") : "question";
}

export function buildScoreTrend(attempts: AttemptOut[]): ScoreTrendPoint[] {
  let totalScore = 0;

  return [...attempts]
    .filter((attempt): attempt is AttemptOut & { score: number } => attempt.score !== null)
    .sort(
      (left, right) =>
        new Date(left.answered_at ?? left.created_at).getTime() -
          new Date(right.answered_at ?? right.created_at).getTime() || left.ordinal - right.ordinal,
    )
    .map((attempt, index) => {
      const timestamp = attempt.answered_at ?? attempt.created_at;
      totalScore += attempt.score;
      return {
        averageScore: totalScore / (index + 1),
        attemptId: attempt.id,
        label: shortLabel(timestamp),
        ordinal: attempt.ordinal,
        questionType: questionTypeLabel(attempt.question_type),
        score: attempt.score,
        timestamp,
      };
    });
}

export interface ClassScoreTrendPoint {
  averageScore: number;
  label: string;
  totalSolved: number;
  studentsIncluded: number;
  timestamp: string;
}

/** The attempt fields the class trend actually reads — satisfied by `AttemptOut`
 * and by the trimmed `scored_attempts` rows from `/api/students/class-summary`. */
export interface ClassTrendAttempt {
  score: number | null;
  answered_at?: string | null;
  created_at: string;
  ordinal: number;
}

export function buildClassScoreTrend(
  attemptsByStudent: Array<{ attempts: ClassTrendAttempt[]; studentId: number }>,
): ClassScoreTrendPoint[] {
  let totalScore = 0;
  const seenStudents = new Set<number>();

  return attemptsByStudent
    .flatMap(({ attempts, studentId }) =>
      attempts.map((attempt) => ({
        attempt,
        studentId,
      })),
    )
    .filter(
      (entry): entry is { attempt: AttemptOut & { score: number }; studentId: number } =>
        entry.attempt.score !== null,
    )
    .sort(
      (left, right) =>
        new Date(left.attempt.answered_at ?? left.attempt.created_at).getTime() -
          new Date(right.attempt.answered_at ?? right.attempt.created_at).getTime() ||
        left.attempt.ordinal - right.attempt.ordinal,
    )
    .map(({ attempt, studentId }, index) => {
      const timestamp = attempt.answered_at ?? attempt.created_at;
      totalScore += attempt.score;
      seenStudents.add(studentId);
      return {
        averageScore: totalScore / (index + 1),
        label: shortLabel(timestamp),
        totalSolved: index + 1,
        studentsIncluded: seenStudents.size,
        timestamp,
      };
    });
}
