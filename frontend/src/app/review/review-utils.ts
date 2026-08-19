import type { QuestionCheck, QuestionDetail, RejectionReason } from "./review-types";
import { REJECTION_REASONS } from "./review-types";

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

export function presentTests(
  value: unknown,
): Array<{ stdin: string; stdout?: string | null; assert?: string | null }> | null {
  if (!Array.isArray(value)) return null;
  const tests = value
    .filter((entry) => typeof entry === "object" && entry !== null)
    .map((entry) => entry as Record<string, unknown>)
    .map((entry) => ({
      stdin: typeof entry.stdin === "string" ? entry.stdin : "",
      stdout: typeof entry.stdout === "string" ? entry.stdout : null,
      assert: typeof entry.assert === "string" ? entry.assert : null,
    }))
    .filter((entry) => entry.stdout || entry.assert);
  return tests.length > 0 ? tests : null;
}

export function explanation(detail: QuestionDetail) {
  return presentText(detail.content?.explanation);
}

export function reviewReasonOptions(
  questionType: QuestionDetail["question"]["question_type"],
): RejectionReason[] {
  const base = REJECTION_REASONS.filter((reason) => reason !== "poor_distractors");
  if (questionType === "multiple_choice") return REJECTION_REASONS.slice();
  return base.filter(
    (reason) =>
      !(
        (reason === "incorrect_tests" || reason === "poor_tests") &&
        !["code_completion", "debugging", "coding"].includes(questionType ?? "")
      ),
  );
}
