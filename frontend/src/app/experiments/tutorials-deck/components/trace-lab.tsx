"use client";

/**
 * The simulator card: one recorded snippet you step through. The code stays central (always
 * visible, the line that just ran marked); the panels beside it are supporting views (variables,
 * branches, the loop test, the call stack, or list memory, depending on the snippet).
 *
 * Prediction is on by default and optional: before the first step, and again at one key moment,
 * the student is asked what happens next. "Just show me" turns it off. Nothing autoplays.
 * Keys: Space or the right arrow steps, the left arrow goes back.
 */

import { RotateCcw, StepBack, StepForward } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { traceById } from "../mock-data";
import type { Trace } from "../traces.generated";
import { CodeView } from "./code-view";
import {
  BranchesPanel,
  CallStackPanel,
  MemoryPanel,
  OutputPanel,
  VariablesPanel,
  WhilePanel,
} from "./panels";
import { useTraceRunner } from "./use-trace-runner";

/** Keys that belong to a field (arrows in a text box or a select) or a control (Space on a button). */
const TYPING = "input,select,textarea,[contenteditable=true]";
const PRESSABLE = "button,a,input,select,textarea,summary";

function Runner({
  trace,
  predictOn,
  setPredictOn,
}: {
  trace: Trace;
  predictOn: boolean;
  setPredictOn: (on: boolean) => void;
}) {
  const run = useTraceRunner(trace, predictOn, setPredictOn);
  const { step, back, current, previous, asking, feedback, atEnd, index, last } = run;
  const stepButton = useRef<HTMLButtonElement>(null);
  const questionBox = useRef<HTMLFieldSetElement>(null);
  const wasAsking = useRef(false);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      const target = event.target instanceof Element ? event.target : null;
      if (target?.closest(TYPING)) return;
      if (event.key === "ArrowRight") {
        event.preventDefault();
        step();
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        back();
      } else if (event.key === " " && !target?.closest(PRESSABLE)) {
        event.preventDefault();
        step();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [step, back]);

  // The choice buttons appear and disappear under the student's hands: keep focus somewhere real.
  useEffect(() => {
    if (asking) questionBox.current?.querySelector("button")?.focus();
    else if (wasAsking.current) stepButton.current?.focus();
    wasAsking.current = asking !== null;
  }, [asking]);

  const view = trace.view;
  const shownOutput = current.output;

  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)] lg:gap-6">
      <div className="min-w-0 space-y-2.5">
        <CodeView
          label="Code"
          code={trace.code}
          current={current.line}
          dim={current.dim}
          paused={current.paused}
        />

        <div className="min-h-[5rem]">
          {asking ? (
            <fieldset
              ref={questionBox}
              aria-label={`Prediction: ${asking.question}`}
              className="m-0 min-w-0 border-0 p-0"
            >
              <p className="font-mono text-[0.68rem] text-muted-foreground uppercase tracking-widest">
                Predict
              </p>
              <p className="mt-0.5 font-medium text-foreground leading-6">{asking.question}</p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                {asking.choices.map((choice, position) => (
                  <Button
                    key={choice}
                    type="button"
                    variant="outline"
                    onClick={() => run.answer(position)}
                    className="h-auto min-h-8 whitespace-normal py-1 text-left font-mono"
                  >
                    {choice}
                  </Button>
                ))}
                <Button type="button" variant="ghost" onClick={run.justShowMe}>
                  Just show me
                </Button>
              </div>
            </fieldset>
          ) : null}
          <div role="status" aria-live="polite" className={cn(asking && "sr-only")}>
            {asking ? `Prediction: ${asking.question}` : null}
            {!asking && feedback ? (
              <p className="leading-6">
                <strong className="font-semibold">
                  {feedback.correct
                    ? "Right. "
                    : `Not quite: it is ${feedback.prediction.choices[feedback.prediction.answer]}. `}
                </strong>
                {feedback.prediction.why}
              </p>
            ) : null}
            {!asking ? <p className="text-foreground leading-6">{current.caption}</p> : null}
            {!asking && atEnd ? (
              <p className="mt-1 font-medium leading-6">
                <span className="sr-only">Rule: </span>
                {trace.takeaway}
              </p>
            ) : null}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button ref={stepButton} type="button" onClick={step} disabled={atEnd || asking !== null}>
            <StepForward aria-hidden="true" />
            Step
          </Button>
          <Button type="button" variant="outline" onClick={back} disabled={index === 0}>
            <StepBack aria-hidden="true" />
            Back
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={run.reset}
            disabled={index === 0 && asking === null}
          >
            <RotateCcw aria-hidden="true" />
            Reset
          </Button>
          <span className="ml-auto font-mono text-muted-foreground text-xs">
            step {index} / {last}
          </span>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 text-muted-foreground text-xs">
          <Button
            type="button"
            variant="ghost"
            size="xs"
            aria-pressed={predictOn}
            onClick={() => setPredictOn(!predictOn)}
          >
            Predict first: {predictOn ? "on" : "off"}
          </Button>
          <span className="hidden sm:inline">Space or right arrow steps, left arrow goes back.</span>
        </div>
      </div>

      <div className="min-w-0 space-y-2.5">
        {view === "branches" ? <BranchesPanel step={current} /> : null}
        {view === "while" ? <WhilePanel step={current} /> : null}
        {view === "memory" ? <MemoryPanel step={current} /> : null}
        {view === "stack" ? <CallStackPanel step={current} previous={previous} /> : null}
        {view === "branches" || view === "while" ? (
          <VariablesPanel step={current} previous={previous} />
        ) : null}
        <OutputPanel lines={shownOutput} endless={trace.endless && atEnd} />
      </div>
    </div>
  );
}

export function TraceLab({
  traceIds,
  predictOn,
  setPredictOn,
}: {
  traceIds: string[];
  predictOn: boolean;
  setPredictOn: (on: boolean) => void;
}) {
  const [activeId, setActiveId] = useState(traceIds[0] ?? "");
  const trace = traceById(activeId);
  return (
    <div className="grid gap-3">
      {traceIds.length > 1 ? (
        <fieldset aria-label="Snippet" className="m-0 flex w-fit rounded-lg border-0 bg-muted p-0.5">
          {traceIds.map((id) => (
            <Button
              key={id}
              type="button"
              size="sm"
              variant={id === activeId ? "outline" : "ghost"}
              aria-pressed={id === activeId}
              onClick={() => setActiveId(id)}
              className="h-6 px-2.5 text-xs"
            >
              {traceById(id).label}
            </Button>
          ))}
        </fieldset>
      ) : null}
      {/* Keyed so switching snippet starts a fresh run. */}
      <Runner key={trace.id} trace={trace} predictOn={predictOn} setPredictOn={setPredictOn} />
    </div>
  );
}
