"use client";

/**
 * Panels the instructor review page shares across several question types. Moved verbatim
 * out of `review-question-content.tsx` so each type file can compose them.
 */

import {
  CodeBlock,
  MissingField,
  ReviewChip,
  statusTone,
} from "@/app/courses/[courseId]/review/components/review-primitives";
import {
  checkByName,
  explanation,
  occurrenceKeys,
  presentTests,
} from "@/app/courses/[courseId]/review/review-utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import type { QuestionDetail } from "@/lib/api/types";

export function ExplanationPanel({ detail }: { detail: QuestionDetail }) {
  const text = explanation(detail);
  if (!text) return null;
  return (
    <Card className="review-panel border">
      <CardHeader>
        <CardTitle>Explanation</CardTitle>
        <CardDescription>Shown to the student after answering.</CardDescription>
      </CardHeader>
      <CardContent>
        <p className="whitespace-pre-wrap text-[14px] text-[var(--review-foreground-2)] leading-7">
          {text}
        </p>
      </CardContent>
    </Card>
  );
}

export function TestsPanel({
  detail,
  isInlineEditing,
  testsEdit,
  onTestsEdit,
}: {
  detail: QuestionDetail;
  isInlineEditing: boolean;
  testsEdit: string;
  onTestsEdit: (value: string) => void;
}) {
  // The row's tests are current (an edit rewrites them); generated content is the fallback.
  const tests = presentTests(detail.tests) ?? presentTests(detail.content?.tests);
  // Reports written before C8 carry the two old checks; newer ones carry one `gradable` check
  // (usable tests and a reference that passes them, via the grader's check_spec).
  const harness = checkByName(detail.validation_checks, "harness_valid");
  const legacyReference = checkByName(detail.validation_checks, "reference_passes_tests");
  const gradable = checkByName(detail.validation_checks, "gradable");
  const reference = legacyReference ?? gradable;
  const referenceLabel = legacyReference?.detail
    ? legacyReference.detail
    : reference?.passed
      ? "reference passes"
      : "reference failed";

  return (
    <Card className="review-panel border">
      <CardHeader>
        <CardTitle>Tests</CardTitle>
        <CardDescription className="flex flex-wrap items-center gap-2">
          {reference ? (
            <ReviewChip tone={statusTone(reference.passed)}>
              {referenceLabel}
            </ReviewChip>
          ) : null}
          {harness ? (
            <ReviewChip tone={statusTone(harness.passed)}>
              {harness.passed ? "harness valid" : "invalid harness"}
            </ReviewChip>
          ) : null}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isInlineEditing ? (
          <Textarea
            rows={8}
            value={testsEdit}
            onChange={(event) => onTestsEdit(event.target.value)}
            className="review-textarea font-mono text-xs"
          />
        ) : !tests ? (
          <MissingField label="Tests are missing." />
        ) : (
          <TestsTable tests={tests} referencePassed={reference?.passed ?? false} />
        )}
      </CardContent>
    </Card>
  );
}

function TestsTable({
  tests,
  referencePassed,
}: {
  tests: Array<{ stdin: string; stdout?: string | null; assert?: string | null }>;
  referencePassed: boolean;
}) {
  const rowKeys = occurrenceKeys(
    tests,
    (test) => `${test.stdin}::${test.stdout ?? ""}::${test.assert ?? ""}`,
  );

  return (
    <div className="overflow-x-auto rounded-[0.8rem] border border-[var(--review-border)] bg-[var(--review-panel)]">
      <table className="w-full text-left text-sm">
        <thead className="bg-[var(--review-panel-2)] font-mono text-[10.5px] text-[var(--review-muted)] uppercase tracking-[0.12em]">
          <tr>
            <th className="px-3 py-2">stdin</th>
            <th className="px-3 py-2">expects</th>
            <th className="px-3 py-2">reference</th>
          </tr>
        </thead>
        <tbody>
          {tests.map((test, index) => (
            <tr key={rowKeys[index]} className="border-[var(--review-border)] border-t">
              <td className="whitespace-pre-wrap px-3 py-2 align-top font-mono text-xs">
                {test.stdin || "--"}
              </td>
              <td className="px-3 py-2 align-top">
                <div className="space-y-1 whitespace-pre-wrap font-mono text-xs">
                  {test.stdout ? <div>stdout: {test.stdout}</div> : null}
                  {test.assert ? <div>{test.assert}</div> : null}
                </div>
              </td>
              <td className="px-3 py-2 align-top text-[var(--review-muted)] text-xs">
                {referencePassed ? "pass" : "see summary"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ReferencePanel({
  title,
  description,
  value,
  isInlineEditing,
  onChange,
  missingLabel,
}: {
  title: string;
  description: string;
  value: string;
  isInlineEditing: boolean;
  onChange: (value: string) => void;
  missingLabel: string;
}) {
  return (
    <Card className="review-panel border">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        {isInlineEditing ? (
          <Textarea
            rows={7}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            className="review-textarea font-mono text-xs"
          />
        ) : value ? (
          <CodeBlock>{value}</CodeBlock>
        ) : (
          <MissingField label={missingLabel} />
        )}
      </CardContent>
    </Card>
  );
}
