"use client";

import { CheckCircle2, XCircle } from "lucide-react";
import {
  CodeBlock,
  ReviewChip,
  statusTone,
} from "@/app/courses/[courseId]/review/components/review-primitives";
import {
  checkByName,
  occurrenceKeys,
  presentStringArray,
} from "@/app/courses/[courseId]/review/review-utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type {
  AnswerInputProps,
  AuthoringReviewProps,
  QuestionTypeUI,
  ReviewContentProps,
} from "./registry";
import { ExplanationPanel } from "./review-panels";
import { CodeAnswerInput } from "./text-answer";

const ANSWER_LABEL = "Choose one answer";

// Radio options, lettered A, B, C... A question served without options falls back to the
// free-text box, as it always has.
function MultipleChoiceAnswerInput(props: AnswerInputProps) {
  const { question, value, onChange } = props;
  if (!question.options) return <CodeAnswerInput {...props} />;
  return (
    <fieldset className="space-y-3">
      <legend className="font-medium text-foreground text-sm">{ANSWER_LABEL}</legend>
      {question.options.map((option, index) => (
        <label
          key={`${question.attempt_id}-${option}`}
          className={cn(
            "group flex cursor-pointer items-start gap-3 rounded-[1.15rem] border p-4 transition-all duration-200",
            value === String(index)
              ? "border-primary/45 bg-primary/8 shadow-[0_16px_34px_-28px_rgb(20_91_84_/_0.55)]"
              : "border-border/70 bg-card/75 hover:border-primary/30 hover:bg-white/90",
          )}
        >
          <input
            type="radio"
            name={`question-${question.attempt_id}`}
            value={index}
            checked={value === String(index)}
            onChange={(event) => onChange(event.target.value)}
            className="mt-1 accent-[var(--accent-solid)]"
          />
          <div className="flex min-w-0 flex-1 items-start justify-between gap-3">
            <span className="text-foreground text-sm leading-7">{option}</span>
            <span
              className={cn(
                "rounded-full px-2 py-1 font-mono text-[10px] uppercase tracking-[0.18em] transition-colors",
                value === String(index)
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground group-hover:bg-accent group-hover:text-accent-foreground",
              )}
            >
              {String.fromCharCode(65 + index)}
            </span>
          </div>
        </label>
      ))}
    </fieldset>
  );
}

// Every option, with the correct one and the student's (wrong) pick marked.
// `submittedAnswer` is the raw option index as a string; absent for a past
// attempt whose historical submission was never retained.
function MultipleChoiceReview({ content, submittedAnswer }: ReviewContentProps) {
  const options = Array.isArray(content.options)
    ? (content.options as unknown[]).filter(
        (option): option is string => typeof option === "string",
      )
    : [];
  const correctIndex =
    typeof content.correct_option_index === "number" ? content.correct_option_index : null;
  if (options.length === 0 || correctIndex === null) return null;
  const chosenIndex =
    submittedAnswer !== undefined && submittedAnswer.trim() !== ""
      ? Number.parseInt(submittedAnswer, 10)
      : null;

  return (
    <div className="space-y-2">
      {options.map((option, index) => {
        const isCorrect = index === correctIndex;
        const isChosenWrong = chosenIndex === index && !isCorrect;
        return (
          <div
            key={option}
            className={cn(
              "flex items-center justify-between gap-3 rounded-[0.9rem] border px-3 py-2 text-sm",
              isCorrect
                ? "border-emerald-500/35 bg-emerald-50 text-emerald-900"
                : isChosenWrong
                  ? "border-rose-500/30 bg-rose-50 text-rose-900"
                  : "border-border/60 bg-muted/10 text-foreground",
            )}
          >
            <span>
              {String.fromCharCode(65 + index)}. {option}
            </span>
            <span className="flex shrink-0 items-center gap-1 font-medium text-xs">
              {isCorrect ? (
                <>
                  <CheckCircle2 className="size-3.5" /> Correct answer
                </>
              ) : null}
              {isChosenWrong ? (
                <>
                  <XCircle className="size-3.5" /> Your answer
                </>
              ) : null}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function MultipleChoiceAuthoringReview({ detail }: AuthoringReviewProps) {
  const checks = detail.validation_checks;
  const content = detail.content ?? {};
  const options = presentStringArray(content.options) ?? [];
  const optionKeys = occurrenceKeys(options, (option) => option);
  const correctIndex =
    typeof content.correct_option_index === "number" ? content.correct_option_index : null;
  const duplicateCheck = checkByName(checks, "mc_no_duplicate_options");
  return (
    <div className="space-y-4">
      <Card className="review-panel border">
        <CardHeader>
          <CardTitle>Options</CardTitle>
          <CardDescription className="flex flex-wrap items-center gap-2">
            <ReviewChip>{options.length} options</ReviewChip>
            {duplicateCheck ? (
              <ReviewChip tone={statusTone(duplicateCheck.passed)}>
                {duplicateCheck.passed ? "no duplicates" : "duplicate options"}
              </ReviewChip>
            ) : null}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {options.map((option, index) => (
            <div
              key={optionKeys[index]}
              className={[
                "flex items-start gap-3 rounded-[0.75rem] border px-3 py-3",
                index === correctIndex
                  ? "review-panel-muted border-[var(--review-accent)]"
                  : "review-panel border",
              ].join(" ")}
            >
              <div className="pt-1 font-mono text-[var(--review-muted)] text-xs">
                {String.fromCharCode(65 + index)}
              </div>
              <div className="grow">
                <CodeBlock>{option}</CodeBlock>
              </div>
              {index === correctIndex ? <ReviewChip tone="accent">correct</ReviewChip> : null}
            </div>
          ))}
        </CardContent>
      </Card>
      <ExplanationPanel detail={detail} />
    </div>
  );
}

export const multipleChoice: QuestionTypeUI = {
  kind: "discrete",
  hasDistractors: true,
  label: "Multiple choice",
  shortLabel: "MCQ",
  answerLabel: ANSWER_LABEL,
  AnswerInput: MultipleChoiceAnswerInput,
  ReviewContent: MultipleChoiceReview,
  AuthoringReview: MultipleChoiceAuthoringReview,
};
