"use client";

/**
 * One trace you step through: the code with the current line marked, the live variables, the output
 * so far, and the step / play / reset controls. Presentational: the position and the play clock live
 * in `useTraceRunner`, the recorded steps in `mock-data.ts`.
 */

import { Pause, Play, RotateCcw, StepForward } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { tokenizePython } from "../../tutorials/components/tutorial-blocks";
import type { Trace } from "../mock-data";
import type { TraceRunner } from "./use-trace-runner";

// The tokenizer is shared with the tutorial reader; its colour map is not exported, so this repeats it.
const TOKEN_CLASS = {
  comment: "text-muted-foreground italic",
  string: "text-emerald-700 dark:text-emerald-400",
  number: "text-amber-700 dark:text-amber-400",
  keyword: "font-medium text-primary",
  builtin: "text-sky-700 dark:text-sky-400",
  plain: "",
} as const;

const MASK = "?";

/** Keys that mean something else when a tab, radio or field has focus. */
const OWN_KEYS = "input,select,textarea,[role=tab],[role=radio]";
const PRESSABLE = "button,a,input,select,textarea,[role=tab]";

function PanelLabel({ children }: { children: ReactNode }) {
  return (
    <h3 className="font-mono text-[0.68rem] text-muted-foreground uppercase tracking-widest">
      {children}
    </h3>
  );
}

function CodeLines({ code, currentLine }: { code: string; currentLine: number | null }) {
  const lines = useMemo(() => code.split("\n").map((text) => tokenizePython(text)), [code]);
  return (
    <ol className="font-mono text-[0.86rem] leading-6">
      {lines.map((tokens, position) => {
        const number = position + 1;
        const current = number === currentLine;
        return (
          <li
            // biome-ignore lint/suspicious/noArrayIndexKey: source lines never reorder
            key={position}
            aria-current={current ? "step" : undefined}
            className={cn(
              "flex border-transparent border-l-2 pr-3",
              current && "border-primary bg-accent",
            )}
          >
            <span
              aria-hidden="true"
              className="w-9 shrink-0 select-none pr-3 text-right text-muted-foreground"
            >
              {number}
            </span>
            <code className="whitespace-pre">
              {tokens.map((token) => (
                <span key={token.at} className={TOKEN_CLASS[token.kind]}>
                  {token.text}
                </span>
              ))}
            </code>
          </li>
        );
      })}
    </ol>
  );
}

export function TracePlayer({
  trace,
  runner,
  masked = false,
  children,
}: {
  trace: Trace;
  runner: TraceRunner;
  /** Hide the trace's `secret` variables and the printed output (the "Now you try" prediction). */
  masked?: boolean;
  /** Extra content under the controls, in the code column. */
  children?: ReactNode;
}) {
  const { index, total, atEnd, playing, fast, reducedMotion, step, reset, togglePlay, setFast } =
    runner;
  const root = useRef<HTMLDivElement>(null);

  const current = index > 0 ? trace.steps[index - 1] : undefined;
  const previous = index > 1 ? trace.steps[index - 2] : undefined;

  /** Every variable the trace ever shows, in the order it first appears. */
  const names = useMemo(() => {
    const seen = new Set<string>();
    for (const item of trace.steps) for (const name of Object.keys(item.vars)) seen.add(name);
    return [...seen];
  }, [trace]);

  // Right arrow and Space step, but only inside this player and never when the key belongs to
  // something else (a tab, a radio, a button that Space already presses).
  useEffect(() => {
    const element = root.current;
    if (!element) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      const target = event.target instanceof Element ? event.target : null;
      if (event.key === "ArrowRight" && !target?.closest(OWN_KEYS)) {
        event.preventDefault();
        step();
      } else if (event.key === " " && !target?.closest(PRESSABLE)) {
        event.preventDefault();
        step();
      }
    };
    element.addEventListener("keydown", onKeyDown);
    return () => element.removeEventListener("keydown", onKeyDown);
  }, [step]);

  const expectation = trace.expectation;
  const showExpectation = expectation !== undefined && index >= expectation.fromStep;
  const showOutput = current?.output ?? [];

  return (
    <div
      ref={root}
      className="grid gap-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] lg:items-start"
    >
      <div className="grid min-w-0 gap-3">
        <section
          // Focusable so Space and the arrow key work once the student has clicked or tabbed to the code.
          // biome-ignore lint/a11y/noNoninteractiveTabindex: a keyboard-operated region, labelled below
          tabIndex={0}
          aria-label="Code. Press Space or the right arrow key to run the next line."
          className="overflow-x-auto rounded-lg border border-border bg-card py-2 outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <CodeLines code={trace.code} currentLine={current?.line ?? null} />
        </section>

        <div className="min-h-[3.25rem]">
          <p role="status" aria-live="polite" className="text-foreground leading-6">
            {current ? current.caption : "Press Step to run the first line."}
            {atEnd && trace.takeaway ? (
              <span className="mt-1 block font-medium">
                <span className="sr-only">Rule: </span>
                {trace.takeaway}
              </span>
            ) : null}
          </p>
        </div>

        <div className="grid gap-2.5">
          <div className="flex items-center gap-3">
            <Progress value={(index / total) * 100} aria-label="Steps run" className="h-1 flex-1" />
            <span className="shrink-0 font-mono text-muted-foreground text-xs">
              {index} / {total}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" onClick={step} disabled={atEnd}>
              <StepForward aria-hidden="true" />
              Step
            </Button>
            <Button type="button" variant="outline" onClick={togglePlay} disabled={reducedMotion}>
              {playing ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
              {playing ? "Pause" : atEnd ? "Replay" : "Play"}
            </Button>
            <fieldset className="m-0 flex min-w-0 rounded-lg border-0 bg-muted p-0.5">
              <legend className="sr-only">Play speed</legend>
              {(
                [
                  ["Slow", false],
                  ["Fast", true],
                ] as const
              ).map(([label, value]) => (
                <Button
                  key={label}
                  type="button"
                  size="sm"
                  variant={fast === value ? "outline" : "ghost"}
                  aria-pressed={fast === value}
                  onClick={() => setFast(value)}
                  className="h-6 px-2 text-xs"
                >
                  {label}
                </Button>
              ))}
            </fieldset>
            <Button type="button" variant="ghost" onClick={reset} disabled={index === 0}>
              <RotateCcw aria-hidden="true" />
              Reset
            </Button>
          </div>
          <p className="text-muted-foreground text-xs">
            {reducedMotion ? (
              "Auto-play is off: your device asks for reduced motion."
            ) : (
              <span className="hidden sm:inline">Keys: Space or the right arrow steps.</span>
            )}
          </p>
        </div>

        {children}
      </div>

      <div className="grid min-w-0 gap-3">
        <div className="rounded-lg border border-border bg-card p-3">
          <PanelLabel>Variables</PanelLabel>
          <div className="mt-2 min-h-[4.5rem]">
            {current ? null : <p className="text-muted-foreground text-xs">Nothing yet.</p>}
            <dl className="grid content-start gap-1 font-mono text-sm">
              {names.map((name) => {
                const value = current?.vars[name];
                if (value === undefined) return null;
                const changed = previous?.vars[name] !== value;
                const hidden = masked && trace.secret.includes(name);
                const mismatch = showExpectation && expectation?.variable === name;
                return (
                  <div key={name} className="flex flex-wrap items-baseline gap-x-3">
                    <dt className="w-20 shrink-0 text-muted-foreground">{name}</dt>
                    <dd className="m-0 flex flex-wrap items-baseline gap-x-3 break-all">
                      <span
                        className={cn(
                          "rounded px-1.5 py-0.5 text-foreground",
                          changed && !hidden && "bg-accent font-medium",
                        )}
                      >
                        {hidden ? MASK : value}
                      </span>
                      {mismatch ? (
                        <span className="font-sans text-destructive text-xs">
                          expected {expectation.expected}
                        </span>
                      ) : null}
                    </dd>
                  </div>
                );
              })}
            </dl>
          </div>
        </div>

        <div className="rounded-lg border border-border bg-card p-3">
          <PanelLabel>Output</PanelLabel>
          {/* aria-live off: the caption already announces what print did. */}
          <output
            aria-live="off"
            aria-label="Program output"
            className="mt-2 block min-h-[4.5rem] font-mono text-sm leading-6"
          >
            {showOutput.length === 0 ? (
              <span className="font-sans text-muted-foreground text-xs">Nothing printed yet.</span>
            ) : (
              showOutput.map((line, position) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: printed lines only ever append
                <span key={position} className="block">
                  {masked && trace.secret.length > 0 ? MASK : line}
                </span>
              ))
            )}
          </output>
        </div>
      </div>
    </div>
  );
}
