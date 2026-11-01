"use client";

import { AlertCircle, CheckCircle2 } from "lucide-react";
import {
  CodeBlock,
  MissingField,
} from "@/app/courses/[courseId]/review/components/review-primitives";
import { checkByName, presentText } from "@/app/courses/[courseId]/review/review-utils";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { AuthoringReviewProps, QuestionTypeUI } from "./registry";
import { ExplanationPanel, ReferencePanel, TestsPanel } from "./review-panels";
import { CODE_ANSWER_LABEL, CodeAnswerInput, NoReviewContent } from "./text-answer";

function DebuggingAuthoringReview(props: AuthoringReviewProps) {
  const { detail, isInlineEditing, referenceEdit, onReferenceEdit } = props;
  const checks = detail.validation_checks;
  const content = detail.content ?? {};
  const broken = presentText(content.code);
  const bugCheck = checkByName(checks, "debug_broken_exhibits_issue");
  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="review-panel border">
          <CardHeader>
            <CardTitle>Broken code</CardTitle>
            <CardDescription>The student should fix this version.</CardDescription>
          </CardHeader>
          <CardContent>
            {broken ? (
              <CodeBlock>{broken}</CodeBlock>
            ) : (
              <MissingField label="Broken code is missing." />
            )}
          </CardContent>
        </Card>
        <ReferencePanel
          title="Fixed reference"
          description="The stored repair."
          value={referenceEdit}
          isInlineEditing={isInlineEditing}
          onChange={onReferenceEdit}
          missingLabel="Reference solution is missing."
        />
      </div>
      <Alert variant={bugCheck?.passed ? "default" : "destructive"}>
        {bugCheck?.passed ? <CheckCircle2 /> : <AlertCircle />}
        <AlertTitle>
          {bugCheck?.passed ? "Bug confirmed" : "Broken code did not exhibit the issue"}
        </AlertTitle>
        <AlertDescription>
          {bugCheck?.evidence ? (
            <p className="whitespace-pre-wrap font-mono text-xs">{bugCheck.evidence}</p>
          ) : (
            <p>{bugCheck?.detail ?? "No deterministic evidence was recorded."}</p>
          )}
        </AlertDescription>
      </Alert>
      <TestsPanel
        detail={detail}
        isInlineEditing={isInlineEditing}
        testsEdit={props.testsEdit}
        onTestsEdit={props.onTestsEdit}
      />
      <ExplanationPanel detail={detail} />
    </div>
  );
}

export const debugging: QuestionTypeUI = {
  kind: "testable_program",
  hasTests: true,
  label: "Debugging",
  shortLabel: "Debugging",
  answerLabel: CODE_ANSWER_LABEL,
  AnswerInput: CodeAnswerInput,
  ReviewContent: NoReviewContent,
  showReferenceSolution: true,
  AuthoringReview: DebuggingAuthoringReview,
};
