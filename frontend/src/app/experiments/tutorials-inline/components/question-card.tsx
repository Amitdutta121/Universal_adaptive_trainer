"use client";

import { ArrowRight, CircleCheck, CircleX } from "lucide-react";
import { type ReactNode, type Ref, useId } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { type Question, TOPIC_LABEL } from "../mock-data";
import { SnippetBlock } from "./snippet-block";

/**
 * One minimal practice question: prompt, code, radio options, submit. After submitting, the options
 * lock and the result sits directly under them, so the reason is read next to the code it explains.
 * The result region is always mounted (it is the aria-live region) and gets focus on submit.
 */
export function QuestionCard({
  question,
  index,
  total,
  pickedId,
  onPick,
  submitted,
  onSubmit,
  headingRef,
  resultRef,
  actions,
}: {
  question: Question;
  index: number;
  total: number;
  pickedId: string | null;
  onPick: (optionId: string) => void;
  submitted: boolean;
  onSubmit: () => void;
  headingRef: Ref<HTMLHeadingElement>;
  resultRef: Ref<HTMLDivElement>;
  /** Buttons under the result (refresher trigger, next). Only rendered once submitted. */
  actions: ReactNode;
}) {
  const fieldId = useId();
  const picked = question.options.find((option) => option.id === pickedId);
  const correct = picked?.correct === true;

  return (
    <section
      aria-labelledby={`${fieldId}-heading`}
      className="space-y-5 rounded-xl border border-border bg-card p-5 ring-1 ring-foreground/5 sm:p-6"
    >
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <h2
            id={`${fieldId}-heading`}
            ref={headingRef}
            tabIndex={-1}
            className="rounded-sm font-heading font-semibold text-foreground text-xl tracking-tight outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            Question {index + 1} of {total}
          </h2>
          <Badge variant="outline">Multiple choice</Badge>
        </div>
        <p className="text-muted-foreground text-sm">{TOPIC_LABEL}</p>
      </header>

      <p className="text-foreground leading-7">{question.prompt}</p>
      <SnippetBlock code={question.code} />

      <fieldset className="space-y-2" disabled={submitted}>
        <legend className="mb-1 font-medium text-foreground text-sm">Choose one answer</legend>
        {question.options.map((option, optionIndex) => {
          const isPicked = option.id === pickedId;
          const showCorrect = submitted && option.correct;
          const showWrong = submitted && isPicked && !option.correct;
          return (
            <label
              key={option.id}
              className={cn(
                "flex items-center gap-3 rounded-lg border p-3 text-sm transition-colors",
                submitted ? "cursor-default" : "cursor-pointer",
                showCorrect && "border-primary bg-primary/5",
                showWrong && "border-destructive/50 bg-destructive/5",
                !showCorrect &&
                  !showWrong &&
                  (isPicked && !submitted
                    ? "border-primary bg-primary/5"
                    : submitted
                      ? "border-border bg-card opacity-60"
                      : "border-border bg-card hover:bg-muted/50"),
              )}
            >
              <input
                type="radio"
                name={`${fieldId}-choice`}
                value={option.id}
                checked={isPicked}
                onChange={() => onPick(option.id)}
                className="size-4 accent-[var(--primary)]"
              />
              <span aria-hidden="true" className="mr-1 font-mono text-muted-foreground text-xs">
                {String.fromCharCode(65 + optionIndex)}
              </span>
              <span className="font-mono text-foreground">{option.text}</span>
              {showCorrect ? (
                <span className="ml-auto flex items-center gap-1 text-primary text-xs">
                  <CircleCheck className="size-3.5" aria-hidden="true" />
                  Correct answer
                </span>
              ) : null}
              {showWrong ? (
                <span className="ml-auto flex items-center gap-1 text-destructive text-xs">
                  <CircleX className="size-3.5" aria-hidden="true" />
                  Your answer
                </span>
              ) : null}
            </label>
          );
        })}
      </fieldset>

      {submitted ? null : (
        <Button
          type="button"
          size="lg"
          onClick={onSubmit}
          disabled={!picked}
          className="w-full sm:w-auto"
        >
          Submit answer
          <ArrowRight />
        </Button>
      )}

      <div
        ref={resultRef}
        tabIndex={-1}
        role="status"
        aria-live="polite"
        className="rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      >
        {submitted && picked ? (
          <div className="space-y-1 border-border border-t pt-4">
            <h3
              className={cn(
                "flex items-center gap-2 font-heading font-semibold text-lg tracking-tight",
                correct ? "text-primary" : "text-destructive",
              )}
            >
              {correct ? (
                <CircleCheck className="size-5" aria-hidden="true" />
              ) : (
                <CircleX className="size-5" aria-hidden="true" />
              )}
              {correct ? "Correct" : "Not quite"}
            </h3>
            <p className="max-w-prose text-foreground text-sm leading-6">{picked.reason}</p>
          </div>
        ) : null}
      </div>

      {submitted ? <div className="flex flex-col gap-2 sm:flex-row">{actions}</div> : null}
    </section>
  );
}
