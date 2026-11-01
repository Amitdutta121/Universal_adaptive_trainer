"use client";

import type { AuthoringReviewProps, QuestionTypeUI } from "./registry";
import { ExplanationPanel, ReferencePanel, TestsPanel } from "./review-panels";
import { CODE_ANSWER_LABEL, CodeAnswerInput, NoReviewContent } from "./text-answer";

function CodingAuthoringReview(props: AuthoringReviewProps) {
  const { detail, isInlineEditing, referenceEdit, onReferenceEdit } = props;
  return (
    <div className="space-y-4">
      <ReferencePanel
        title="Reference solution"
        description="The current stored answer."
        value={referenceEdit}
        isInlineEditing={isInlineEditing}
        onChange={onReferenceEdit}
        missingLabel="Reference solution is missing."
      />
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

export const coding: QuestionTypeUI = {
  kind: "testable_program",
  hasTests: true,
  label: "Coding",
  shortLabel: "Coding",
  answerLabel: CODE_ANSWER_LABEL,
  AnswerInput: CodeAnswerInput,
  ReviewContent: NoReviewContent,
  showReferenceSolution: true,
  AuthoringReview: CodingAuthoringReview,
};
