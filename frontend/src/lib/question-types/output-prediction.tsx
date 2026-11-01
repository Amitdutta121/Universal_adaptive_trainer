"use client";

import {
  CodeBlock,
  MissingField,
  ReviewChip,
  statusTone,
} from "@/app/courses/[courseId]/review/components/review-primitives";
import { checkByName, presentText } from "@/app/courses/[courseId]/review/review-utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type {
  AnswerInputProps,
  AuthoringReviewProps,
  QuestionTypeUI,
  ReviewContentProps,
} from "./registry";
import { ExplanationPanel } from "./review-panels";
import { TextAnswerInput } from "./text-answer";

const ANSWER_LABEL = "Your answer";

function OutputPredictionAnswerInput(props: AnswerInputProps) {
  return (
    <TextAnswerInput {...props} label={ANSWER_LABEL} rows={6} placeholder="Type the exact output" />
  );
}

// Expected stdout side by side with what the student actually typed.
function OutputPredictionReview({ content, submittedAnswer }: ReviewContentProps) {
  const expected = typeof content.expected_output === "string" ? content.expected_output : null;
  if (expected === null) return null;

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <div className="space-y-1">
        <div className="font-medium text-[11px] text-muted-foreground uppercase tracking-[0.14em]">
          Expected output
        </div>
        <pre className="overflow-x-auto whitespace-pre-wrap rounded-lg border border-border/70 bg-muted/20 p-3 font-mono text-foreground text-xs leading-6">
          {expected}
        </pre>
      </div>
      {submittedAnswer !== undefined ? (
        <div className="space-y-1">
          <div className="font-medium text-[11px] text-muted-foreground uppercase tracking-[0.14em]">
            Your output
          </div>
          <pre className="overflow-x-auto whitespace-pre-wrap rounded-lg border border-border/70 bg-muted/20 p-3 font-mono text-foreground text-xs leading-6">
            {submittedAnswer.trim() === "" ? "(nothing submitted)" : submittedAnswer}
          </pre>
        </div>
      ) : null}
    </div>
  );
}

function OutputPredictionAuthoringReview({ detail }: AuthoringReviewProps) {
  const checks = detail.validation_checks;
  const content = detail.content ?? {};
  const source = presentText(content.code);
  const expected = presentText(content.expected_output);
  const observed = checkByName(checks, "expected_output_verified");
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_20rem]">
      <Card className="review-panel border">
        <CardHeader>
          <CardTitle>Code</CardTitle>
          <CardDescription>The student reads and reasons about this script.</CardDescription>
        </CardHeader>
        <CardContent>
          {source ? <CodeBlock>{source}</CodeBlock> : <MissingField label="Code is missing." />}
        </CardContent>
      </Card>
      <div className="space-y-4">
        <Card className="review-panel border">
          <CardHeader>
            <CardTitle>Expected output</CardTitle>
            <CardDescription>What the generator claimed.</CardDescription>
          </CardHeader>
          <CardContent>
            {expected ? (
              <CodeBlock>{expected}</CodeBlock>
            ) : (
              <MissingField label="Expected output is missing." />
            )}
          </CardContent>
        </Card>
        <Card className="review-panel border">
          <CardHeader>
            <CardTitle>Observed by deterministic check</CardTitle>
            <CardDescription>
              {observed?.passed
                ? "Matches the claimed output."
                : "Interpreter evidence from validation."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {observed?.evidence ? (
              <CodeBlock>{observed.evidence}</CodeBlock>
            ) : (
              <ReviewChip tone={statusTone(observed?.passed)}>
                {observed?.passed ? "verified" : "no observed output recorded"}
              </ReviewChip>
            )}
          </CardContent>
        </Card>
        <ExplanationPanel detail={detail} />
      </div>
    </div>
  );
}

export const outputPrediction: QuestionTypeUI = {
  kind: "testable_program",
  label: "Output prediction",
  shortLabel: "Output",
  answerLabel: ANSWER_LABEL,
  AnswerInput: OutputPredictionAnswerInput,
  ReviewContent: OutputPredictionReview,
  AuthoringReview: OutputPredictionAuthoringReview,
};
