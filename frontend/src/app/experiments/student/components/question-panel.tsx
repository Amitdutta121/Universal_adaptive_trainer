"use client";

import { AlertCircle, ArrowDown, ArrowRight, ArrowUp, Flame, RotateCcw } from "lucide-react";
import { useId } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { questionTypeLabel, type SelectionResult } from "../mock-data";

function DifficultyBadge({ difficulty }: { difficulty: SelectionResult["servedDifficulty"] }) {
  return (
    <Badge variant="outline" className="capitalize">
      {difficulty}
    </Badge>
  );
}

function ParsonsComposer({
  order,
  stepText,
  onReorder,
}: {
  order: string[];
  stepText: (id: string) => string;
  onReorder: (nextOrder: string[]) => void;
}) {
  const move = (from: number, to: number) => {
    if (to < 0 || to >= order.length) return;
    const next = [...order];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    onReorder(next);
  };

  return (
    <ol className="space-y-2">
      {order.map((id, index) => (
        <li
          key={id}
          className="flex items-stretch gap-2 rounded-lg border border-border bg-card p-2"
        >
          <span
            className="flex w-6 shrink-0 items-center justify-center rounded-md bg-muted font-mono text-muted-foreground text-xs"
            aria-hidden="true"
          >
            {index + 1}
          </span>
          <pre className="min-w-0 flex-1 overflow-x-auto whitespace-pre px-1 py-1.5 font-mono text-foreground text-xs leading-5">
            {stepText(id)}
          </pre>
          <div className="flex shrink-0 flex-col gap-1">
            <Button
              type="button"
              variant="outline"
              size="icon-sm"
              onClick={() => move(index, index - 1)}
              disabled={index === 0}
              aria-label={`Move step ${index + 1} up`}
            >
              <ArrowUp className="size-3.5" />
            </Button>
            <Button
              type="button"
              variant="outline"
              size="icon-sm"
              onClick={() => move(index, index + 1)}
              disabled={index === order.length - 1}
              aria-label={`Move step ${index + 1} down`}
            >
              <ArrowDown className="size-3.5" />
            </Button>
          </div>
        </li>
      ))}
    </ol>
  );
}

export function QuestionPanel({
  selection,
  answer,
  onAnswerChange,
  parsonsOrder,
  onParsonsReorder,
  onSubmit,
  submitting,
  submitError,
  onRetry,
  streak,
}: {
  selection: SelectionResult;
  answer: string;
  onAnswerChange: (value: string) => void;
  parsonsOrder: string[];
  onParsonsReorder: (nextOrder: string[]) => void;
  onSubmit: () => void;
  submitting: boolean;
  submitError: string | null;
  onRetry: () => void;
  streak: number;
}) {
  const { question } = selection;
  const fieldId = useId();
  const stepById = new Map((question.steps ?? []).map((step) => [step.id, step]));

  const hasAnswer =
    question.type === "parsons"
      ? parsonsOrder.length > 0
      : question.type === "multiple_choice" || question.type === "true_false"
        ? answer !== ""
        : answer.trim() !== "";
  const canSubmit = hasAnswer && !submitting;

  return (
    <section
      aria-labelledby={`${fieldId}-heading`}
      className="space-y-5 rounded-xl border border-border bg-card p-5 ring-1 ring-foreground/5 sm:p-6"
    >
      <header className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2
            id={`${fieldId}-heading`}
            className="font-heading font-semibold text-foreground text-xl tracking-tight"
          >
            Question {selection.ordinal}
          </h2>
          <DifficultyBadge difficulty={selection.servedDifficulty} />
          <Badge variant="outline">{questionTypeLabel(question.type)}</Badge>
          {streak >= 2 ? (
            <Badge className="gap-1 bg-amber-500/15 text-amber-700 dark:text-amber-300">
              <Flame className="size-3.5" aria-hidden="true" />
              {streak} in a row
            </Badge>
          ) : null}
        </div>
        <p className="text-muted-foreground text-sm">
          {question.topicName} · {question.subtopicName}
        </p>
      </header>

      {selection.fallbackUsed ? (
        <Alert>
          <AlertCircle />
          <AlertTitle>Difficulty adjusted</AlertTitle>
          <AlertDescription>
            Your progress in {question.topicName} called for a{" "}
            <strong>{selection.requestedDifficulty}</strong> question, but this set only had a{" "}
            <strong>{selection.servedDifficulty}</strong> one left for {question.subtopicName}.
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="whitespace-pre-wrap rounded-lg border border-border bg-background/60 p-4 text-foreground leading-7">
        {question.prompt}
      </div>

      {question.code ? (
        <pre className="overflow-x-auto rounded-lg border border-border bg-muted/60 p-4 font-mono text-foreground text-sm leading-6">
          {question.code}
        </pre>
      ) : null}

      {question.type === "multiple_choice" ? (
        <fieldset className="space-y-2">
          <legend className="mb-1 font-medium text-foreground text-sm">Choose one answer</legend>
          {(question.options ?? []).map((option, index) => (
            <label
              key={option}
              className={cn(
                "flex cursor-pointer items-start gap-3 rounded-lg border p-3 text-sm transition-colors",
                answer === String(index)
                  ? "border-primary bg-primary/5"
                  : "border-border bg-card hover:bg-muted/50",
              )}
            >
              <input
                type="radio"
                name={`${fieldId}-choice`}
                value={index}
                checked={answer === String(index)}
                onChange={(event) => onAnswerChange(event.target.value)}
                className="mt-0.5 size-4 accent-[var(--primary)]"
              />
              <span className="text-foreground leading-6">
                <span className="mr-2 font-mono text-muted-foreground text-xs">
                  {String.fromCharCode(65 + index)}
                </span>
                {option}
              </span>
            </label>
          ))}
        </fieldset>
      ) : null}

      {question.type === "true_false" ? (
        <fieldset className="space-y-2">
          <legend className="mb-1 font-medium text-foreground text-sm">True or false</legend>
          {[
            ["true", "True"],
            ["false", "False"],
          ].map(([value, label]) => (
            <label
              key={value}
              className={cn(
                "flex cursor-pointer items-center gap-3 rounded-lg border p-3 text-sm transition-colors",
                answer === value
                  ? "border-primary bg-primary/5"
                  : "border-border bg-card hover:bg-muted/50",
              )}
            >
              <input
                type="radio"
                name={`${fieldId}-bool`}
                value={value}
                checked={answer === value}
                onChange={(event) => onAnswerChange(event.target.value)}
                className="size-4 accent-[var(--primary)]"
              />
              <span className="font-medium text-foreground">{label}</span>
            </label>
          ))}
        </fieldset>
      ) : null}

      {question.type === "parsons" ? (
        <div className="space-y-2">
          <p className="font-medium text-foreground text-sm">
            Order the steps
            <span className="ml-2 font-normal text-muted-foreground">
              — use the arrow buttons to move a line up or down.
            </span>
          </p>
          <ParsonsComposer
            order={parsonsOrder}
            stepText={(id) => stepById.get(id)?.text ?? id}
            onReorder={onParsonsReorder}
          />
        </div>
      ) : null}

      {question.type === "short_text" || question.type === "output_prediction" ? (
        <div className="space-y-2">
          <label className="font-medium text-foreground text-sm" htmlFor={`${fieldId}-text`}>
            {question.type === "output_prediction" ? "Type the exact output" : "Type your answer"}
          </label>
          <Textarea
            id={`${fieldId}-text`}
            value={answer}
            onChange={(event) => onAnswerChange(event.target.value)}
            onKeyDown={(event) => {
              if ((event.metaKey || event.ctrlKey) && event.key === "Enter" && canSubmit) {
                event.preventDefault();
                onSubmit();
              }
            }}
            rows={question.type === "output_prediction" ? 3 : 4}
            className="font-mono text-sm"
            placeholder={question.type === "output_prediction" ? "e.g. 42" : "Type your answer"}
          />
          <p className="text-muted-foreground text-xs">
            Tip: press Ctrl+Enter (⌘+Enter on Mac) to submit.
          </p>
        </div>
      ) : null}

      {submitError ? (
        <Alert variant="destructive">
          <AlertCircle />
          <AlertTitle>Couldn't save your answer</AlertTitle>
          <AlertDescription>
            <p>{submitError}</p>
            <p>Your answer is still here — retry when you're ready.</p>
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="flex flex-col gap-3 rounded-lg border border-border bg-muted/30 p-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-muted-foreground text-sm">
          Once you submit, this answer is scored and locked in.
        </p>
        {submitError ? (
          <Button type="button" size="lg" onClick={onRetry} className="w-full sm:w-auto">
            <RotateCcw />
            Retry submit
          </Button>
        ) : (
          <Button
            type="button"
            size="lg"
            onClick={onSubmit}
            disabled={!canSubmit}
            className="w-full sm:w-auto"
          >
            {submitting ? "Scoring…" : "Submit answer"}
            {submitting ? null : <ArrowRight />}
          </Button>
        )}
      </div>
    </section>
  );
}
