/**
 * The numbers behind the learning charts, from a class's scored answers. Pure: the prototype runs
 * it on mock and snapshot data, and the real chart can run it on rows from the API unchanged.
 *
 * Every rate carries its count and a 95% Wilson interval, and is flagged `enough` only from
 * `MIN_N` answers, so a chart can show a thin point as thin instead of as a trend.
 */

export type Difficulty = "easy" | "medium" | "hard";

/** One scored answer. A class's answers are passed oldest first. */
export interface Answer {
  student: string;
  subtopic: string;
  difficulty: Difficulty;
  correct: boolean;
  /** When it was answered (ISO, UTC); only the over-time chart reads it. */
  at?: string;
}

/** Answers below this count are drawn, but not as evidence. */
export const MIN_N = 5;

export interface Rate {
  n: number;
  correct: number;
  /** 0–100, or null with no answers. */
  rate: number | null;
  low: number | null;
  high: number | null;
  enough: boolean;
}

/** Share correct with its 95% Wilson interval, in percent. */
export function rateOf(correct: number, n: number): Rate {
  if (n === 0) return { n, correct, rate: null, low: null, high: null, enough: false };
  const z = 1.96;
  const p = correct / n;
  const centre = (p + (z * z) / (2 * n)) / (1 + (z * z) / n);
  const half = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / (1 + (z * z) / n);
  return {
    n,
    correct,
    rate: 100 * p,
    low: 100 * Math.max(0, centre - half),
    high: 100 * Math.min(1, centre + half),
    enough: n >= MIN_N,
  };
}

/** Each student's answers on each subtopic, in order: one sequence of right/wrong per pair. */
export function sequences(answers: readonly Answer[]): Map<string, boolean[]> {
  const bySequence = new Map<string, boolean[]>();
  for (const answer of answers) {
    const key = `${answer.student}\u0000${answer.subtopic}`;
    const list = bySequence.get(key) ?? [];
    list.push(answer.correct);
    bySequence.set(key, list);
  }
  return bySequence;
}

export interface ExploredPoint extends Rate {
  /** How many different subtopics the student had reached by this answer. */
  explored: number;
  students: number;
}

/**
 * Average score by how many different subtopics the student had reached when answering. An
 * answer counts at the student's count at that moment, so a return to an earlier subtopic counts
 * at the higher number. Scores here are right or wrong, so the average is the share correct.
 */
export function bySubtopicsExplored(answers: readonly Answer[]): ExploredPoint[] {
  const reached = new Map<string, Set<string>>();
  const tally = new Map<number, { right: number; n: number; students: Set<string> }>();
  for (const answer of answers) {
    const seen = reached.get(answer.student) ?? new Set<string>();
    seen.add(answer.subtopic);
    reached.set(answer.student, seen);
    const entry = tally.get(seen.size) ?? { right: 0, n: 0, students: new Set<string>() };
    entry.n += 1;
    if (answer.correct) entry.right += 1;
    entry.students.add(answer.student);
    tally.set(seen.size, entry);
  }
  return [...tally.entries()]
    .sort(([left], [right]) => left - right)
    .map(([explored, entry]) => ({
      explored,
      students: entry.students.size,
      ...rateOf(entry.right, entry.n),
    }));
}

export interface DifficultyScore extends Rate {
  difficulty: Difficulty;
  students: number;
}

/** Average score at each served difficulty, easy to hard: a check that the labels hold up. */
export function byDifficulty(answers: readonly Answer[]): DifficultyScore[] {
  return (["easy", "medium", "hard"] as const).map((difficulty) => {
    const at = answers.filter((answer) => answer.difficulty === difficulty);
    return {
      difficulty,
      students: new Set(at.map((answer) => answer.student)).size,
      ...rateOf(at.filter((answer) => answer.correct).length, at.length),
    };
  });
}

export interface TimeBucket {
  /** Start of the day or week, ISO date (UTC). */
  start: string;
  unit: "day" | "week";
  easy: Rate;
  medium: Rate;
  hard: Rate;
  total: number;
}

const DAY_MS = 86_400_000;

/**
 * Share correct at each difficulty per calendar period: days when the answers span three weeks
 * or less, otherwise weeks starting Monday (UTC). Empty periods in between are kept, so the axis
 * is true time. Answers without `at` are left out.
 */
export function byDifficultyOverTime(answers: readonly Answer[]): TimeBucket[] {
  const timed = answers.filter((answer) => answer.at);
  if (timed.length === 0) return [];
  const times = timed.map((answer) => Date.parse(answer.at as string));
  const first = Math.min(...times);
  const last = Math.max(...times);
  const unit: TimeBucket["unit"] = last - first <= 21 * DAY_MS ? "day" : "week";
  const floor = (time: number) => {
    const day = Math.floor(time / DAY_MS) * DAY_MS;
    if (unit === "day") return day;
    const weekday = (new Date(day).getUTCDay() + 6) % 7; // Monday = 0
    return day - weekday * DAY_MS;
  };
  const step = unit === "day" ? DAY_MS : 7 * DAY_MS;
  const tally = new Map<number, Record<Difficulty, [number, number]>>();
  for (let start = floor(first); start <= floor(last); start += step) {
    tally.set(start, { easy: [0, 0], medium: [0, 0], hard: [0, 0] });
  }
  timed.forEach((answer, index) => {
    const counts = tally.get(floor(times[index]));
    if (!counts) return;
    counts[answer.difficulty][1] += 1;
    if (answer.correct) counts[answer.difficulty][0] += 1;
  });
  return [...tally.entries()].map(([start, counts]) => ({
    start: new Date(start).toISOString().slice(0, 10),
    unit,
    easy: rateOf(...counts.easy),
    medium: rateOf(...counts.medium),
    hard: rateOf(...counts.hard),
    total: counts.easy[1] + counts.medium[1] + counts.hard[1],
  }));
}

export interface CurvePoint extends Rate {
  opportunity: number;
}

/**
 * Share correct at a student's 1st, 2nd, … answer on a subtopic.
 *
 * `everyone` uses every sequence that reached that answer, so each point is a different mix of
 * students: an adaptive tutor moves the quick ones on, and later points are only who is left.
 * `cohort` uses only sequences with at least `k` answers, for answers 1..k: the same students at
 * every point, which is the curve to read as learning. They are the students who needed `k`
 * answers, so the cohort starts lower than the class.
 */
export function learningCurve(
  answers: readonly Answer[],
  k: number,
  maxOpportunity = 8,
): { everyone: CurvePoint[]; cohort: CurvePoint[]; cohortSize: number } {
  const all = [...sequences(answers).values()];
  const everyone: CurvePoint[] = [];
  for (let j = 1; j <= maxOpportunity; j++) {
    const reached = all.filter((sequence) => sequence.length >= j);
    if (reached.length === 0) break;
    const right = reached.filter((sequence) => sequence[j - 1]).length;
    everyone.push({ opportunity: j, ...rateOf(right, reached.length) });
  }
  const long = all.filter((sequence) => sequence.length >= k);
  const cohort: CurvePoint[] = [];
  for (let j = 1; j <= k && long.length > 0; j++) {
    const right = long.filter((sequence) => sequence[j - 1]).length;
    cohort.push({ opportunity: j, ...rateOf(right, long.length) });
  }
  return { everyone, cohort, cohortSize: long.length };
}

export interface FirstLatest {
  subtopic: string;
  first: Rate;
  latest: Rate;
  improved: number;
  same: number;
  worse: number;
}

/**
 * First against latest answer, for every student who answered a subtopic at least twice: per
 * subtopic, and over all subtopics (`subtopic` "All subtopics").
 */
export function firstVsLatest(answers: readonly Answer[]): FirstLatest[] {
  const pairs = new Map<string, [boolean, boolean][]>();
  for (const [key, sequence] of sequences(answers)) {
    if (sequence.length < 2) continue;
    const subtopic = key.split("\u0000")[1];
    const list = pairs.get(subtopic) ?? [];
    list.push([sequence[0], sequence[sequence.length - 1]]);
    pairs.set(subtopic, list);
  }
  const summarise = (subtopic: string, list: [boolean, boolean][]): FirstLatest => ({
    subtopic,
    first: rateOf(list.filter(([first]) => first).length, list.length),
    latest: rateOf(list.filter(([, latest]) => latest).length, list.length),
    improved: list.filter(([first, latest]) => !first && latest).length,
    same: list.filter(([first, latest]) => first === latest).length,
    worse: list.filter(([first, latest]) => first && !latest).length,
  });
  const rows = [...pairs.entries()].map(([subtopic, list]) => summarise(subtopic, list));
  return [summarise("All subtopics", [...pairs.values()].flat()), ...rows];
}

export interface DifficultyBucket {
  label: string;
  easy: Rate;
  medium: Rate;
  hard: Rate;
}

/**
 * Share correct at each difficulty, by answer number on the subtopic (1, 2, …, `buckets`+): the
 * learning curve split by difficulty. Comparing like with like keeps the harder questions a
 * student earns by doing well from reading as forgetting. By answer on the subtopic, not on the
 * student's whole history, because every new subtopic starts them over.
 */
export function byDifficultyAndAnswer(answers: readonly Answer[], buckets = 4): DifficultyBucket[] {
  const seen = new Map<string, number>();
  const tally = Array.from({ length: buckets }, () => ({
    easy: [0, 0],
    medium: [0, 0],
    hard: [0, 0],
  }));
  for (const answer of answers) {
    const key = `${answer.student}\u0000${answer.subtopic}`;
    const index = seen.get(key) ?? 0;
    seen.set(key, index + 1);
    const bucket = tally[Math.min(index, buckets - 1)];
    bucket[answer.difficulty][1] += 1;
    if (answer.correct) bucket[answer.difficulty][0] += 1;
  }
  return tally.map((bucket, index) => ({
    label: index === buckets - 1 ? `${index + 1}+` : `${index + 1}`,
    easy: rateOf(bucket.easy[0], bucket.easy[1]),
    medium: rateOf(bucket.medium[0], bucket.medium[1]),
    hard: rateOf(bucket.hard[0], bucket.hard[1]),
  }));
}
