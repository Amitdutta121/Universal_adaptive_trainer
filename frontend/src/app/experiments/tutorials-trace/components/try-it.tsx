"use client";

/**
 * "Now you try": a new snippet the student can step through, but its `total` stays hidden until they
 * have picked a prediction and pressed Reveal.
 */

import { CircleCheck, CircleX } from "lucide-react";
import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { TRY_ANSWER, TRY_CHOICES, TRY_TRACE } from "../mock-data";
import { TracePlayer } from "./trace-player";
import { useTraceRunner } from "./use-trace-runner";

export function TryIt() {
  const runner = useTraceRunner(TRY_TRACE);
  const [choice, setChoice] = useState<string | null>(null);
  const [revealed, setRevealed] = useState(false);
  const headingId = useId();
  const groupName = useId();

  const reveal = () => {
    setRevealed(true);
    runner.jumpToEnd();
  };

  const picked = TRY_CHOICES.find((option) => option.value === choice);
  const correct = choice === TRY_ANSWER;

  return (
    <section aria-labelledby={headingId} className="border-border border-t pt-6">
      <h2 id={headingId} className="font-heading font-semibold text-foreground text-lg">
        Now you try
      </h2>
      <p className="mt-1 mb-4 text-muted-foreground text-sm">
        Predict the final total, then reveal.
      </p>

      <TracePlayer trace={TRY_TRACE} runner={runner} masked={!revealed}>
        <fieldset className="grid gap-2 border-0 p-0" disabled={revealed}>
          <legend className="mb-1 font-medium text-foreground text-sm">total ends at</legend>
          <div className="flex flex-wrap gap-2">
            {TRY_CHOICES.map((option) => (
              <label
                key={option.value}
                className={cn(
                  "flex min-w-16 cursor-pointer items-center justify-center rounded-lg border px-4 py-1.5 font-mono text-sm transition-colors",
                  "has-[:focus-visible]:border-ring has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring/50",
                  choice === option.value
                    ? "border-primary bg-accent"
                    : "border-border bg-card hover:bg-muted",
                  revealed && "cursor-default",
                )}
              >
                <input
                  type="radio"
                  name={groupName}
                  value={option.value}
                  checked={choice === option.value}
                  onChange={() => setChoice(option.value)}
                  className="sr-only"
                />
                {option.value}
              </label>
            ))}
            <Button type="button" onClick={reveal} disabled={choice === null || revealed}>
              Reveal
            </Button>
          </div>
        </fieldset>

        <div role="status" aria-live="polite" className="min-h-6 text-sm leading-6">
          {revealed && picked ? (
            <p className="flex items-start gap-2 text-foreground">
              {correct ? (
                <CircleCheck className="mt-1 size-4 shrink-0 text-primary" aria-hidden="true" />
              ) : (
                <CircleX className="mt-1 size-4 shrink-0 text-destructive" aria-hidden="true" />
              )}
              <span>
                {correct ? `Yes, ${TRY_ANSWER}. ` : `Not ${picked.value}. `}
                {picked.why}
                {correct ? "" : ` It ends at ${TRY_ANSWER}.`}
              </span>
            </p>
          ) : null}
        </div>
      </TracePlayer>
    </section>
  );
}
