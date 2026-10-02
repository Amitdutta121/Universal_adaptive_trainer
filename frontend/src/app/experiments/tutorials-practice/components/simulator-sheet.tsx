"use client";

/**
 * Rung 2 of the help ladder: a step-through simulator of the question's own code, in a side panel
 * (a bottom sheet on a phone). The SOURCE CODE stays central; the variables, the output and the
 * caption only support it. The student's chosen answer is pinned next to what the code really prints,
 * so the mismatch is visible without a lecture.
 *
 * "Try it yourself" makes the code editable: change a condition, a `return`, a list operation, press
 * Run, and step through the new version. Nothing here plays by itself.
 *
 * TODO(real): a real system would run the code in a sandbox (Pyodide or a server) and record the
 * trace from CPython; the mini-runner in `../mini-python` is the prototype stand-in.
 */

import {
  ChevronLeft,
  ChevronsRight,
  CircleCheck,
  CircleX,
  Pencil,
  Play,
  RotateCcw,
  StepForward,
} from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  captionFor,
  changedVars,
  condenseOutput,
  type FrameSnap,
  type RunResult,
  type Step,
} from "../mini-python";
import { CodeLines, Inline } from "./code-view";
import { describeFailure, useSimulator } from "./use-simulator";

export interface Pinned {
  /** "Your answer" or "You wanted". */
  label: string;
  text: string;
  /** Label for what the code really does, e.g. "Actual output". */
  actualLabel: string;
  /** Does what the student pinned describe what this run really did? */
  matches: (result: RunResult) => boolean;
}

/** The output panel of the pinned comparison, as text. */
export function describeActual(result: RunResult): string {
  const printed = condenseOutput(result.output);
  switch (result.status) {
    case "ok":
      return printed || "(nothing printed)";
    case "limit":
      return `${printed}\n(never ends)`.trim();
    case "error":
      return [printed, `${result.error?.name}: ${result.error?.message}`]
        .filter(Boolean)
        .join("\n");
    case "syntax":
      return result.error?.name ?? "SyntaxError";
    default:
      return "Not supported yet";
  }
}

function useWideScreen(): boolean {
  const [wide, setWide] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const query = window.matchMedia("(min-width: 768px)");
    const update = () => setWide(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return wide;
}

const LABEL = "font-mono text-[0.68rem] text-muted-foreground uppercase tracking-widest";

// ---- panels ---------------------------------------------------------------------------------

function PinnedCompare({ pinned, result }: { pinned: Pinned; result: RunResult }) {
  const matches = pinned.matches(result);
  return (
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border bg-border">
      <div className="min-w-0 bg-card p-2.5">
        <span className={LABEL}>{pinned.label}</span>
        <pre className="mt-1 max-h-20 overflow-auto whitespace-pre-wrap break-words font-mono text-[0.82rem] leading-5">
          {pinned.text}
        </pre>
      </div>
      <div className="min-w-0 bg-card p-2.5" role="status" aria-live="polite">
        <span className={cn(LABEL, "flex items-center gap-1.5")}>
          {pinned.actualLabel}
          {matches ? (
            <CircleCheck className="size-3.5 text-primary" aria-hidden="true" />
          ) : (
            <CircleX className="size-3.5 text-destructive" aria-hidden="true" />
          )}
          <span className="sr-only">{matches ? "matches" : "does not match"}</span>
        </span>
        <pre className="mt-1 max-h-20 overflow-auto whitespace-pre-wrap break-words font-mono text-[0.82rem] leading-5">
          {describeActual(result)}
        </pre>
      </div>
    </div>
  );
}

function VariablesPanel({ step, changed }: { step: Step; changed: Set<string> }) {
  const shown = step.frames.map((frame, frameIndex) => ({
    frame,
    frameIndex,
    vars: frame.vars.filter((v) => v.type !== "function"),
  }));
  const listCount = new Map<number, number>();
  for (const { vars } of shown) {
    for (const v of vars) {
      if (v.listId !== undefined) listCount.set(v.listId, (listCount.get(v.listId) ?? 0) + 1);
    }
  }
  const empty = shown.every(({ vars }) => vars.length === 0) && step.frames.length === 1;

  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <h3 className={LABEL}>Variables</h3>
      {empty ? <p className="mt-2 text-muted-foreground text-xs">Nothing yet.</p> : null}
      <div className="mt-2 grid gap-2.5">
        {shown.map(({ frame, frameIndex, vars }) =>
          frame.isModule && vars.length === 0 ? null : (
            <FrameView
              key={`${frameIndex}:${frame.label}`}
              frame={frame}
              frameIndex={frameIndex}
              vars={vars}
              showLabel={step.frames.length > 1}
              changed={changed}
              listCount={listCount}
            />
          ),
        )}
      </div>
    </div>
  );
}

function FrameView({
  frame,
  frameIndex,
  vars,
  showLabel,
  changed,
  listCount,
}: {
  frame: FrameSnap;
  frameIndex: number;
  vars: FrameSnap["vars"];
  showLabel: boolean;
  changed: Set<string>;
  listCount: Map<number, number>;
}) {
  return (
    <section
      aria-label={`Frame ${frame.label}`}
      className={cn(showLabel && "border-border border-l-2 pl-2.5")}
    >
      {showLabel ? (
        <p className="mb-1 font-mono text-muted-foreground text-xs">{frame.label}</p>
      ) : null}
      <dl className="grid content-start gap-1 font-mono text-sm">
        {vars.map((v) => {
          const shared = v.listId !== undefined && (listCount.get(v.listId) ?? 0) > 1;
          return (
            <div key={v.name} className="flex flex-wrap items-baseline gap-x-3">
              <dt className="w-16 shrink-0 text-muted-foreground">{v.name}</dt>
              <dd className="m-0 flex min-w-0 flex-wrap items-baseline gap-x-2 break-all">
                <span
                  className={cn(
                    "rounded px-1.5 py-0.5 text-foreground",
                    changed.has(`${frameIndex}:${v.name}`) && "bg-accent font-medium",
                  )}
                >
                  {v.repr}
                </span>
                {v.listId !== undefined ? (
                  <span
                    className={cn(
                      "font-sans text-xs",
                      shared ? "font-medium text-primary" : "text-muted-foreground",
                    )}
                  >
                    {shared ? `same list #${v.listId}` : `list #${v.listId}`}
                  </span>
                ) : null}
              </dd>
            </div>
          );
        })}
      </dl>
    </section>
  );
}

// ---- body -----------------------------------------------------------------------------------

function SimulatorBody({ code, pinned }: { code: string; pinned: Pinned }) {
  const sim = useSimulator(code);
  const { result, index, mode } = sim;
  const step = result.steps[index];
  const codeRef = useRef<HTMLElement>(null);

  // Keep the current line in view inside the code panel, without smooth scrolling.
  // biome-ignore lint/correctness/useExhaustiveDependencies: re-run whenever the step changes
  useEffect(() => {
    const current = codeRef.current?.querySelector('[aria-current="step"]');
    if (current && typeof current.scrollIntoView === "function") {
      current.scrollIntoView({ block: "nearest", behavior: "auto" });
    }
  }, [index, sim.source]);

  const changed = step ? changedVars(result.steps, index) : new Set<string>();
  // Code that never got as far as a trace (a syntax error, e.g. a badly ordered program).
  const failure = describeFailure(result);
  const atEnd = index >= sim.last;
  const editing = mode === "edit";

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 pb-3">
      <PinnedCompare pinned={pinned} result={result} />

      <div className="flex flex-wrap items-center justify-between gap-2">
        <fieldset className="m-0 flex min-w-0 rounded-lg border-0 bg-muted p-0.5">
          <legend className="sr-only">Mode</legend>
          <Button
            type="button"
            size="sm"
            variant={editing ? "ghost" : "outline"}
            aria-pressed={!editing}
            onClick={sim.stopEditing}
            className="h-6 px-2 text-xs"
          >
            Watch
          </Button>
          <Button
            type="button"
            size="sm"
            variant={editing ? "outline" : "ghost"}
            aria-pressed={editing}
            onClick={sim.startEditing}
            className="h-6 px-2 text-xs"
          >
            <Pencil aria-hidden="true" />
            Try it yourself
          </Button>
        </fieldset>
        {sim.edited ? (
          <Button type="button" variant="ghost" size="sm" onClick={sim.restoreOriginal}>
            Restore original
          </Button>
        ) : null}
      </div>

      {editing ? (
        <div className="grid gap-2">
          <label htmlFor="sim-code" className="sr-only">
            Python code. Edit it, then press Run.
          </label>
          <Textarea
            id="sim-code"
            value={sim.draft}
            onChange={(event) => sim.setDraft(event.target.value.slice(0, 2000))}
            spellCheck={false}
            autoCapitalize="off"
            autoCorrect="off"
            rows={Math.min(Math.max(sim.draft.split("\n").length, 4), 12)}
            wrap="off"
            className="max-h-[40dvh] overflow-auto whitespace-pre font-mono text-[0.84rem] leading-6"
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" onClick={sim.runDraft}>
              <Play aria-hidden="true" />
              Run
            </Button>
            <span className="text-muted-foreground text-xs">Then step through your version.</span>
          </div>
          <p role="status" aria-live="polite" className="min-h-5 text-destructive text-sm">
            {sim.notice}
          </p>
        </div>
      ) : (
        <>
          <section
            ref={codeRef}
            // Focusable so a keyboard user can scroll a long program.
            // biome-ignore lint/a11y/noNoninteractiveTabindex: a scrollable region, labelled below
            tabIndex={0}
            aria-label="Code"
            className="max-h-[30dvh] overflow-auto rounded-lg border border-border bg-muted/60 py-2 outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 md:max-h-[40dvh]"
          >
            <CodeLines
              code={sim.source}
              currentLine={step?.line ?? (failure ? (result.error?.line ?? null) : null)}
              errorLine={step?.kind === "error" || Boolean(failure)}
            />
          </section>

          <div className="min-h-[3.25rem] text-sm leading-6" role="status" aria-live="polite">
            {step?.kind === "error" ? (
              <>
                <p className="font-medium text-destructive">{step.message}</p>
                <p className="text-foreground">{result.error?.plain}</p>
              </>
            ) : step ? (
              <p className="text-foreground">
                <Inline text={captionFor(result.steps, index)} />
              </p>
            ) : failure ? (
              <>
                <p className="font-medium text-destructive">
                  {result.error ? `${result.error.name}: ${result.error.message}` : failure}
                </p>
                {result.error ? <p className="text-foreground">{result.error.plain}</p> : null}
              </>
            ) : null}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="outline" onClick={sim.back} disabled={index === 0}>
              <ChevronLeft aria-hidden="true" />
              Back
            </Button>
            <Button type="button" onClick={sim.step} disabled={atEnd}>
              <StepForward aria-hidden="true" />
              Step
            </Button>
            <Button type="button" variant="ghost" onClick={sim.toEnd} disabled={atEnd}>
              <ChevronsRight aria-hidden="true" />
              To the end
            </Button>
            <Button type="button" variant="ghost" onClick={sim.reset} disabled={index === 0}>
              <RotateCcw aria-hidden="true" />
              Reset
            </Button>
            {result.steps.length > 0 ? (
              <span className="ml-auto font-mono text-muted-foreground text-xs">
                {index + 1} / {result.steps.length}
              </span>
            ) : null}
          </div>

          {step ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <VariablesPanel step={step} changed={changed} />
              <div className="rounded-lg border border-border bg-card p-3">
                <h3 className={LABEL}>Output so far</h3>
                {/* aria-live off: the caption already announces what print did. */}
                <output
                  aria-live="off"
                  aria-label="Program output"
                  className="mt-2 block max-h-40 min-h-6 overflow-auto whitespace-pre font-mono text-sm leading-6"
                >
                  {step.output ? (
                    condenseOutput(step.output)
                  ) : (
                    <span className="font-sans text-muted-foreground text-xs">
                      Nothing printed yet.
                    </span>
                  )}
                </output>
              </div>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

// ---- sheet ----------------------------------------------------------------------------------

/**
 * The trigger lives here so Radix returns focus to it when the sheet closes (Escape, the X, the
 * overlay). `onExplain` closes the sheet and opens rung 3; the parent then moves focus itself.
 */
export function SimulatorSheet({
  code,
  pinned,
  trigger,
  open,
  onOpenChange,
  onExplain,
  onCloseAutoFocus,
}: {
  code: string;
  pinned: Pinned;
  trigger: ReactNode;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onExplain?: () => void;
  onCloseAutoFocus?: (event: Event) => void;
}) {
  const wide = useWideScreen();
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetTrigger asChild>{trigger}</SheetTrigger>
      <SheetContent
        side={wide ? "right" : "bottom"}
        onCloseAutoFocus={onCloseAutoFocus}
        className={cn(
          "gap-3 data-[side=bottom]:max-h-[90dvh] data-[side=right]:w-full data-[side=right]:sm:max-w-xl",
          "motion-reduce:transition-none motion-reduce:data-closed:animate-none motion-reduce:data-open:animate-none",
        )}
      >
        <SheetHeader className="pr-12 pb-0">
          <SheetTitle>What the code does</SheetTitle>
          <SheetDescription className="sr-only">
            Step through the question&rsquo;s code one line at a time. The marked line is the one
            that runs next.
          </SheetDescription>
        </SheetHeader>
        <SimulatorBody code={code} pinned={pinned} />
        {onExplain ? (
          <SheetFooter className="border-border border-t pt-3">
            <Button type="button" variant="outline" onClick={onExplain}>
              Explain it like a worked example
            </Button>
          </SheetFooter>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
