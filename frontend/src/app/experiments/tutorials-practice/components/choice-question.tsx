"use client";

import { CircleCheck, CircleX } from "lucide-react";
import { useId } from "react";
import { cn } from "@/lib/utils";
import type { ChoiceQuestion as ChoiceQuestionData } from "../mock-data";
import { CodeBlock } from "./code-view";

/**
 * "What does this print?" with radio options. A wrong pick is marked and disabled (the student
 * keeps the rest to try again); once the question is finished the correct option is marked too.
 */
export function ChoiceQuestion({
  question,
  pickedId,
  onPick,
  wrongIds,
  finished,
  correctId,
}: {
  question: ChoiceQuestionData;
  pickedId: string | null;
  onPick: (optionId: string) => void;
  wrongIds: string[];
  finished: boolean;
  correctId: string;
}) {
  const name = useId();
  return (
    <>
      <p className="font-medium text-foreground">What does this print?</p>
      <CodeBlock code={question.code} label="Code to read" />
      <fieldset className="space-y-2 border-0 p-0" disabled={finished}>
        <legend className="sr-only">Choose one answer</legend>
        {question.options.map((option, position) => {
          const wrong = wrongIds.includes(option.id);
          const isPicked = option.id === pickedId && !wrong;
          const showCorrect = finished && option.id === correctId;
          return (
            <label
              key={option.id}
              className={cn(
                "flex items-start gap-3 rounded-lg border p-3 text-sm transition-colors",
                "has-[:focus-visible]:border-ring has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring/50",
                wrong || finished ? "cursor-default" : "cursor-pointer",
                showCorrect && "border-primary bg-primary/5",
                wrong && "border-border bg-card opacity-60",
                !showCorrect &&
                  !wrong &&
                  (isPicked
                    ? "border-primary bg-primary/5"
                    : "border-border bg-card hover:bg-muted/50"),
              )}
            >
              <input
                type="radio"
                name={name}
                value={option.id}
                checked={isPicked}
                disabled={wrong}
                onChange={() => onPick(option.id)}
                className="mt-1 size-4 accent-[var(--primary)]"
              />
              <span aria-hidden="true" className="mt-0.5 font-mono text-muted-foreground text-xs">
                {String.fromCharCode(65 + position)}
              </span>
              <span className="min-w-0 flex-1 whitespace-pre-wrap break-words font-mono text-foreground">
                {option.text}
              </span>
              {wrong ? (
                <span className="flex shrink-0 items-center gap-1 text-destructive text-xs">
                  <CircleX className="size-3.5" aria-hidden="true" />
                  Missed
                </span>
              ) : null}
              {showCorrect ? (
                <span className="flex shrink-0 items-center gap-1 text-primary text-xs">
                  <CircleCheck className="size-3.5" aria-hidden="true" />
                  Correct answer
                </span>
              ) : null}
            </label>
          );
        })}
      </fieldset>
    </>
  );
}
