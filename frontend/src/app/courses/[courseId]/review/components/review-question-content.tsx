"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { type AuthoringReviewProps, questionTypeUI } from "@/lib/question-types/registry";
import { CodeBlock, ReviewChip } from "./review-primitives";

type ReviewQuestionContentProps = AuthoringReviewProps;

export function ReviewQuestionSurface({
  detail,
  isInlineEditing,
  promptEdit,
  onPromptEdit,
}: Pick<ReviewQuestionContentProps, "detail" | "isInlineEditing" | "promptEdit" | "onPromptEdit">) {
  return (
    <Card className="review-panel border">
      <CardHeader>
        <div className="review-eyebrow">Question surface</div>
        <CardTitle className="flex flex-wrap items-center gap-2">
          <span>Question {detail.question.id}</span>
          <ReviewChip>{detail.question.difficulty}</ReviewChip>
          <ReviewChip tone="accent">
            {detail.question.question_type ?? detail.question.kind}
          </ReviewChip>
        </CardTitle>
        <CardDescription>
          {detail.taxonomy.topic} - {detail.taxonomy.subtopics.join(", ")}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {isInlineEditing ? (
          <Textarea
            rows={7}
            value={promptEdit}
            onChange={(event) => onPromptEdit(event.target.value)}
            className="review-textarea"
          />
        ) : (
          <p className="whitespace-pre-wrap text-[15px] text-[var(--review-foreground)] leading-7">
            {detail.question.prompt}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

export function ReviewQuestionContent(props: ReviewQuestionContentProps) {
  const { detail, referenceEdit } = props;
  const typeUI = questionTypeUI(detail.question.question_type);
  if (typeUI) return <typeUI.AuthoringReview {...props} />;

  return (
    <Card className="review-panel border">
      <CardHeader>
        <CardTitle>Question body</CardTitle>
        <CardDescription>This question has no specialized renderer yet.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="whitespace-pre-wrap text-[14px] leading-7">{detail.question.prompt}</p>
        {referenceEdit ? <CodeBlock>{referenceEdit}</CodeBlock> : null}
      </CardContent>
    </Card>
  );
}
