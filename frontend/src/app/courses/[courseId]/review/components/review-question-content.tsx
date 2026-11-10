"use client";

import { QuestionBody } from "@/components/question-body";
import { QuestionFigureCopies } from "@/components/question-figure-copies";
import { QuestionFigureEditor } from "@/components/question-figure-editor";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import type { QuestionFigure } from "@/lib/api/types";
import { type AuthoringReviewProps, questionTypeUI } from "@/lib/question-types/registry";
import { CodeBlock, ReviewChip } from "./review-primitives";

type ReviewQuestionContentProps = AuthoringReviewProps;

export function ReviewQuestionSurface({
  detail,
  isInlineEditing,
  promptEdit,
  onPromptEdit,
  figureEdit = null,
  onFigureEdit,
  onFigureError,
}: Pick<ReviewQuestionContentProps, "detail" | "isInlineEditing" | "promptEdit" | "onPromptEdit"> & {
  figureEdit?: QuestionFigure | null;
  onFigureEdit?: (figure: QuestionFigure) => void;
  onFigureError?: (message: string | null) => void;
}) {
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
          {detail.question.live_generated ? <ReviewChip tone="warn">Live</ReviewChip> : null}
        </CardTitle>
        <CardDescription>
          {detail.taxonomy.topic} - {detail.taxonomy.subtopics.join(", ")}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {isInlineEditing ? (
          <>
            <Textarea
              rows={7}
              value={promptEdit}
              onChange={(event) => onPromptEdit(event.target.value)}
              className="review-textarea"
            />
            {figureEdit && onFigureEdit && onFigureError ? (
              <QuestionFigureEditor
                key={detail.question.id}
                figure={figureEdit}
                onChange={onFigureEdit}
                onError={onFigureError}
              />
            ) : null}
          </>
        ) : (
          <QuestionBody
            prompt={detail.question.prompt}
            figure={detail.question.figure}
            promptClassName="text-[15px] text-[var(--review-foreground)]"
          />
        )}
        <QuestionFigureCopies detail={detail} />
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
        <QuestionBody
          prompt={detail.question.prompt}
          figure={detail.question.figure}
          promptClassName="text-[14px]"
        />
        {referenceEdit ? <CodeBlock>{referenceEdit}</CodeBlock> : null}
      </CardContent>
    </Card>
  );
}
