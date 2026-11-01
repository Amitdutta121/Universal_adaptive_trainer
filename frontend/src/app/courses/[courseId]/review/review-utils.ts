import type { QuestionCheck, QuestionDetail } from "./review-types";

export function labelize(value: string) {
  return value.replace(/_/g, " ");
}

export function occurrenceKeys<T>(items: T[], identity: (item: T) => string) {
  const seen = new Map<string, number>();
  return items.map((item) => {
    const base = identity(item);
    const count = seen.get(base) ?? 0;
    seen.set(base, count + 1);
    return `${base}-${count}`;
  });
}

export function checkByName(checks: QuestionCheck[], name: string) {
  return checks.find((check) => check.name === name) ?? null;
}

export function presentText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

export function presentStringArray(value: unknown): string[] | null {
  return Array.isArray(value) && value.every((item) => typeof item === "string")
    ? (value as string[])
    : null;
}

// Deterministic shuffle for the "Blocks" preview only -- purely presentational,
// so a professor sees roughly what a student's shuffled puzzle looks like
// without this preview ever touching what actually gets served (that shuffle
// lives server-side in `_presentable_blocks`, seeded on the attempt id).
// Same seed always produces the same order, so it doesn't reshuffle on every render.
function seededShuffle<T>(items: T[], seed: number): T[] {
  const shuffled = [...items];
  let state = seed || 1;
  const next = () => {
    // mulberry32
    state |= 0;
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(next() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  return shuffled;
}

export function presentBlocksShuffled(
  value: unknown,
  seed: number,
): Array<{ id: string; text: string; indent: number }> | null {
  const blocks = presentBlocks(value);
  return blocks && blocks.length > 1 ? seededShuffle(blocks, seed) : blocks;
}

export function presentBlocks(
  value: unknown,
): Array<{ id: string; text: string; indent: number }> | null {
  if (!Array.isArray(value)) return null;
  const blocks = value
    .filter((entry) => typeof entry === "object" && entry !== null)
    .map((entry) => entry as Record<string, unknown>)
    .filter(
      (entry) =>
        typeof entry.id === "string" &&
        typeof entry.text === "string" &&
        typeof entry.indent === "number",
    )
    .map((entry) => ({
      id: entry.id as string,
      text: entry.text as string,
      indent: entry.indent as number,
    }));
  return blocks.length > 0 ? blocks : null;
}

/**
 * The question's test cases, from either stored shape: the row's `tests` column (a JSON
 * string whose entries carry `assert`) or the generated `content.tests` list (entries carry
 * `assert_code`). Returns null when there is no usable test.
 */
export function presentTests(
  value: unknown,
): Array<{ stdin: string; stdout?: string | null; assert?: string | null }> | null {
  if (typeof value === "string") {
    try {
      return presentTests(JSON.parse(value));
    } catch {
      return null;
    }
  }
  if (!Array.isArray(value)) return null;
  const tests = value
    .filter((entry) => typeof entry === "object" && entry !== null)
    .map((entry) => entry as Record<string, unknown>)
    .map((entry) => {
      const assertion = entry.assert ?? entry.assert_code;
      return {
        stdin: typeof entry.stdin === "string" ? entry.stdin : "",
        stdout: typeof entry.stdout === "string" ? entry.stdout : null,
        assert: typeof assertion === "string" ? assertion : null,
      };
    })
    .filter((entry) => entry.stdout || entry.assert);
  return tests.length > 0 ? tests : null;
}

export function explanation(detail: QuestionDetail) {
  return presentText(detail.content?.explanation);
}
