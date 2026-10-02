"use client";

import { ReviewChip } from "@/app/courses/[courseId]/review/components/review-primitives";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import type {
  AnswerInputProps,
  AuthoringReviewProps,
  QuestionTypeUI,
  ReviewContentProps,
} from "./registry";
import { ExplanationPanel } from "./review-panels";

const ANSWER_LABEL = "True or false";

function TrueFalseAnswerInput({ question, value: answer, onChange }: AnswerInputProps) {
  return (
    <fieldset className="space-y-3">
      <legend className="font-medium text-foreground text-sm">{ANSWER_LABEL}</legend>
      {[
        ["true", "True"],
        ["false", "False"],
      ].map(([value, label]) => (
        <label
          key={value}
          className={cn(
            "flex cursor-pointer items-center gap-3 rounded-[1.15rem] border p-4 transition-all duration-200",
            answer === value
              ? "border-primary/45 bg-primary/8 shadow-[0_16px_34px_-28px_rgb(20_91_84_/_0.55)]"
              : "border-border/70 bg-card/75 hover:border-primary/30 hover:bg-white/90",
          )}
        >
          <input
            type="radio"
            name={`question-${question.attempt_id}`}
            value={value}
            checked={answer === value}
            onChange={(event) => onChange(event.target.value)}
            className="accent-[var(--accent-solid)]"
          />
          <span className="font-medium text-foreground text-sm">{label}</span>
        </label>
      ))}
    </fieldset>
  );
}

// Correct true/false answer, plus the student's answer only when it was
// actually wrong (matching correct answers add nothing worth reading).
function TrueFalseReview({ content, submittedAnswer }: ReviewContentProps) {
  const correct = content.correct_answer;
  if (typeof correct !== "boolean") return null;
  const correctLabel = correct ? "True" : "False";
  const submittedNormalized = submittedAnswer?.trim().toLowerCase();
  const submittedLabel =
    submittedNormalized === "true" ? "True" : submittedNormalized === "false" ? "False" : null;

  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <Badge variant="secondary">Correct answer: {correctLabel}</Badge>
      {submittedLabel && submittedLabel !== correctLabel ? (
        <Badge variant="destructive">Your answer: {submittedLabel}</Badge>
      ) : null}
    </div>
  );
}

function TrueFalseAuthoringReview({ detail }: AuthoringReviewProps) {
  const content = detail.content ?? {};
  const correct = typeof content.correct_answer === "boolean" ? content.correct_answer : null;
  return (
    <div className="space-y-4">
      <Card className="review-panel border">
        <CardHeader>
          <CardTitle>Answer</CardTitle>
          <CardDescription>Compact key for the binary claim.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-center gap-2">
            <ReviewChip tone={correct === true ? "ok" : "muted"}>True</ReviewChip>
            <ReviewChip tone={correct === false ? "ok" : "muted"}>False</ReviewChip>
            <Separator orientation="vertical" className="hidden h-4 sm:block" />
            <span className="text-[var(--review-muted)] text-xs">
              {typeof correct === "boolean"
                ? "boolean answer recorded"
                : "answer missing"}
            </span>
          </div>
        </CardContent>
      </Card>
      <ExplanationPanel detail={detail} />
    </div>
  );
}

export const trueFalse: QuestionTypeUI = {
  kind: "discrete",
  label: "True / false",
  shortLabel: "T/F",
  answerLabel: ANSWER_LABEL,
  AnswerInput: TrueFalseAnswerInput,
  ReviewContent: TrueFalseReview,
  AuthoringReview: TrueFalseAuthoringReview,
};
