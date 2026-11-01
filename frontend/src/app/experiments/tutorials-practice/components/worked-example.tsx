"use client";

import { ArrowRight, CircleCheck } from "lucide-react";
import { type Ref, useId, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { runProgram } from "../mini-python";
import type { Misconception } from "../mock-data";
import { checkFaded } from "../practice-logic";
import { CodeBlock, CodeLines, Inline } from "./code-view";

/**
 * Rung 3: a short worked example for the misconception, then the same idea with the last line
 * blanked. The student's line is run together with the rest, so any correct line passes, not just
 * the one in the answer key. "Try another" always works: nothing here is a gate.
 */
export function WorkedExample({
  misconception,
  headingRef,
  onTryAnother,
  isLast,
}: {
  misconception: Misconception;
  headingRef: Ref<HTMLHeadingElement>;
  onTryAnother: () => void;
  isLast: boolean;
}) {
  const inputId = useId();
  const [typed, setTyped] = useState("");
  const [feedback, setFeedback] = useState("");
  const [state, setState] = useState<"open" | "passed" | "revealed">("open");

  const { worked, faded } = misconception;
  const workedOutput = useMemo(() => runProgram(worked.code).output, [worked.code]);
  const stemLines = faded.stem.split("\n").length - 1;

  const check = () => {
    const outcome = checkFaded(misconception, typed);
    if (outcome.passed) {
      setFeedback("");
      setState("passed");
    } else {
      setFeedback(outcome.feedback);
    }
  };

  const reveal = () => {
    setTyped(faded.answer);
    setFeedback("");
    setState("revealed");
  };

  const done = state !== "open";

  return (
    <section
      aria-labelledby={`${inputId}-heading`}
      className="space-y-3 border-border border-t pt-4"
    >
      <h3
        id={`${inputId}-heading`}
        ref={headingRef}
        tabIndex={-1}
        className="rounded-sm font-heading font-semibold text-base text-foreground tracking-tight outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      >
        Worked example
      </h3>
      <p className="text-foreground text-sm leading-6">
        <Inline text={worked.note} />
      </p>
      <CodeBlock code={worked.code} output={workedOutput} label="Worked example" />

      <p className="pt-1 font-medium text-foreground text-sm">Now you finish one. {faded.goal}</p>
      <div className="overflow-hidden rounded-lg border border-border bg-muted/60">
        <div className="overflow-x-auto py-2.5">
          <CodeLines code={faded.stem} />
        </div>
        <div className="flex items-center gap-2 border-border border-t bg-background/60 py-2 pr-3 pl-2">
          <span
            aria-hidden="true"
            className="w-8 shrink-0 select-none pr-2.5 text-right font-mono text-[0.84rem] text-muted-foreground"
          >
            {stemLines + 1}
          </span>
          {faded.indent ? (
            <span aria-hidden="true" className="whitespace-pre font-mono text-[0.84rem]">
              {faded.indent}
            </span>
          ) : null}
          <label htmlFor={inputId} className="sr-only">
            The last line of the program
          </label>
          <Input
            id={inputId}
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !done) check();
            }}
            disabled={state === "passed" || state === "revealed"}
            spellCheck={false}
            autoCapitalize="off"
            autoCorrect="off"
            autoComplete="off"
            placeholder="Type the last line"
            className="font-mono md:text-[0.84rem]"
          />
        </div>
      </div>

      <div role="status" aria-live="polite" className="min-h-6 text-sm leading-6">
        {state === "passed" ? (
          <p className="flex items-center gap-2 text-primary">
            <CircleCheck className="size-4 shrink-0" aria-hidden="true" />
            That prints {faded.expected.trim().replace(/\n/g, ", ")}.
          </p>
        ) : null}
        {state === "revealed" ? (
          <p className="text-muted-foreground">The last line was shown above.</p>
        ) : null}
        {feedback ? <p className="text-destructive">{feedback}</p> : null}
      </div>

      <div className="flex flex-col gap-2 sm:flex-row">
        {done ? null : (
          <>
            <Button type="button" onClick={check} disabled={typed.trim() === ""}>
              Check
            </Button>
            <Button type="button" variant="ghost" onClick={reveal}>
              Show the line
            </Button>
          </>
        )}
        <Button type="button" variant={done ? "default" : "outline"} onClick={onTryAnother}>
          {isLast ? "See summary" : "Try another"}
          <ArrowRight aria-hidden="true" />
        </Button>
      </div>
    </section>
  );
}
