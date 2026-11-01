"use client";

import {
  CodeBlock,
  MissingField,
  ReviewChip,
} from "@/app/courses/[courseId]/review/components/review-primitives";
import { occurrenceKeys, presentText } from "@/app/courses/[courseId]/review/review-utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { AuthoringReviewProps, QuestionTypeUI } from "./registry";
import { ExplanationPanel, ReferencePanel, TestsPanel } from "./review-panels";
import { CODE_ANSWER_LABEL, CodeAnswerInput, NoReviewContent } from "./text-answer";

function computeAddedLines(stub: string, reference: string) {
  const stubLines = stub.replace(/\r\n/g, "\n").split("\n");
  const referenceLines = reference.replace(/\r\n/g, "\n").split("\n");
  const added = new Set<number>();
  let stubIndex = 0;

  referenceLines.forEach((line, index) => {
    if (stubIndex < stubLines.length && line === stubLines[stubIndex]) {
      stubIndex += 1;
      return;
    }
    added.add(index);
  });

  return { stubLines, referenceLines, addedCount: added.size, added };
}

function CodeCompletionDiff({ stub, reference }: { stub: string; reference: string }) {
  const { stubLines, referenceLines, addedCount, added } = computeAddedLines(stub, reference);
  const stubKeys = occurrenceKeys(stubLines, (line) => line);
  const referenceKeys = occurrenceKeys(referenceLines, (line) => line);

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card className="review-panel border">
        <CardHeader>
          <div className="flex items-center gap-2">
            <CardTitle>Given to the student</CardTitle>
            <ReviewChip>stub</ReviewChip>
          </div>
        </CardHeader>
        <CardContent>
          <div className="review-diff-shell">
            <pre className="review-diff-code">
              {stubLines.map((line, index) => (
                <div key={`stub-${stubKeys[index]}`} className="review-diff-line">
                  {line || " "}
                </div>
              ))}
            </pre>
          </div>
        </CardContent>
      </Card>

      <Card className="review-panel border">
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <CardTitle>Reference solution</CardTitle>
              <ReviewChip>key</ReviewChip>
            </div>
            <span className="review-diff-meta">
              +{addedCount} {addedCount === 1 ? "line" : "lines"} over the stub
            </span>
          </div>
        </CardHeader>
        <CardContent>
          <div className="review-diff-shell">
            <pre className="review-diff-code">
              {referenceLines.map((line, index) => (
                <div
                  key={`ref-${referenceKeys[index]}`}
                  className={
                    added.has(index)
                      ? "review-diff-line review-diff-line-added"
                      : "review-diff-line"
                  }
                >
                  {line || " "}
                </div>
              ))}
            </pre>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function CodeCompletionAuthoringReview(props: AuthoringReviewProps) {
  const { detail, isInlineEditing, referenceEdit, onReferenceEdit } = props;
  const content = detail.content ?? {};
  const source = presentText(content.code);
  return (
    <div className="space-y-4">
      {isInlineEditing ? (
        <div className="grid gap-4 xl:grid-cols-2">
          <Card className="review-panel border">
            <CardHeader>
              <CardTitle>Given to the student</CardTitle>
              <CardDescription>The stub and its gap.</CardDescription>
            </CardHeader>
            <CardContent>
              {source ? <CodeBlock>{source}</CodeBlock> : <MissingField label="Stub is missing." />}
            </CardContent>
          </Card>
          <ReferencePanel
            title="Reference solution"
            description="The full key, read as what the stub needs."
            value={referenceEdit}
            isInlineEditing={isInlineEditing}
            onChange={onReferenceEdit}
            missingLabel="Reference solution is missing."
          />
        </div>
      ) : source && referenceEdit ? (
        <CodeCompletionDiff stub={source} reference={referenceEdit} />
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          <Card className="review-panel border">
            <CardHeader>
              <CardTitle>Given to the student</CardTitle>
            </CardHeader>
            <CardContent>
              {source ? <CodeBlock>{source}</CodeBlock> : <MissingField label="Stub is missing." />}
            </CardContent>
          </Card>
          <ReferencePanel
            title="Reference solution"
            description="The full key, read as what the stub needs."
            value={referenceEdit}
            isInlineEditing={false}
            onChange={onReferenceEdit}
            missingLabel="Reference solution is missing."
          />
        </div>
      )}
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

export const codeCompletion: QuestionTypeUI = {
  kind: "testable_program",
  hasTests: true,
  label: "Code completion",
  shortLabel: "Completion",
  answerLabel: CODE_ANSWER_LABEL,
  AnswerInput: CodeAnswerInput,
  ReviewContent: NoReviewContent,
  showReferenceSolution: true,
  AuthoringReview: CodeCompletionAuthoringReview,
};
