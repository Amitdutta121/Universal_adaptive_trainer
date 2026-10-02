"use client";

/**
 * What the sheet will cost, and the button that spends it.
 *
 * Every number here comes from `/api/questions/batch-plan` — the same compiler
 * that runs the batch — so what is shown is what will happen rather than a second
 * opinion computed in the browser.
 */

import { AlertTriangle, Loader2, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { BatchPlanTotals } from "../spec-sheet-types";

/** Above this, a synchronous run is long enough that the professor should be told. */
const LONG_RUN_QUESTIONS = 12;

function Figure({
  label,
  value,
  tone = "plain",
}: {
  label: string;
  value: string;
  tone?: "plain" | "accent";
}) {
  return (
    <span className="flex flex-col gap-0.5">
      <span className="font-mono text-[0.62rem] text-muted-foreground uppercase tracking-[0.14em]">
        {label}
      </span>
      <span
        className={[
          "font-mono font-semibold text-base tabular-nums",
          tone === "accent" ? "text-primary" : "text-foreground",
        ].join(" ")}
      >
        {value}
      </span>
    </span>
  );
}

export function RunSummary({
  totals,
  isPricing,
  isRunning,
  canRun,
  onRun,
}: {
  totals: BatchPlanTotals | null;
  isPricing: boolean;
  isRunning: boolean;
  canRun: boolean;
  onRun: () => void;
}) {
  const questions = totals?.questions_to_create ?? 0;
  const isLongRun = questions >= LONG_RUN_QUESTIONS;

  return (
    <div className="flex flex-col gap-3 border-border/70 border-t bg-muted/25 px-5 py-4">
      <div className="flex flex-wrap items-center gap-x-8 gap-y-3">
        <Figure label="Chunks" value={String(totals?.chunks_specified ?? 0)} />
        <Figure label="Questions" value={String(questions)} tone="accent" />
        <Figure
          label="E / M / H"
          value={`${totals?.easy ?? 0} / ${totals?.medium ?? 0} / ${totals?.hard ?? 0}`}
        />
        <Figure label="Generation calls" value={String(totals?.generation_calls ?? 0)} />
        <Figure label="Judge calls" value={String(totals?.judge_calls ?? 0)} />

        <Button
          type="button"
          className="ml-auto"
          disabled={!canRun || questions === 0 || isRunning || isPricing}
          onClick={onRun}
        >
          {isRunning ? (
            <>
              <Loader2 className="size-4 animate-spin" /> Generating {questions}...
            </>
          ) : (
            <>
              <Play className="size-4" />{" "}
              {!canRun
                ? "Upload taxonomy to generate"
                : questions === 0
                  ? "Nothing specified yet"
                  : `Generate ${questions} questions`}
            </>
          )}
        </Button>
      </div>

      {totals && totals.identical_repeats > 0 ? (
        <p className="flex items-start gap-2 text-[color:var(--warn-solid)] text-xs">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
          <span>
            {totals.identical_repeats} of these repeat a chunk, difficulty and format already asked
            for. Nothing currently makes a repeat differ from the question it repeats — choose more
            formats for those chunks, or expect near-duplicates.
          </span>
        </p>
      ) : null}

      {isLongRun && !isRunning ? (
        <p className="text-muted-foreground text-xs">
          This run is made in sequence — one generation call plus its judge calls per question — and
          it holds one request open until it finishes. Keep the tab open.
        </p>
      ) : null}

      {!canRun ? (
        <p className="text-muted-foreground text-xs">
          Question generation is blocked until one curriculum taxonomy is approved.
        </p>
      ) : null}

      {isRunning ? (
        <p className="text-muted-foreground text-xs">
          Generating in sequence. Questions are saved one at a time, so anything already produced is
          kept even if the run is interrupted.
        </p>
      ) : null}
    </div>
  );
}
