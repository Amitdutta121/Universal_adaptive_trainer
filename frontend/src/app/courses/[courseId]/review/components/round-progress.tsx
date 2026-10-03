"use client";

import { Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import type { GenerationRound } from "../review-types";

export function NextRoundButton({
  canStart,
  isStarting,
  disabledReason,
  onStart,
}: {
  canStart: boolean;
  isStarting: boolean;
  disabledReason: string | null;
  onStart: () => void;
}) {
  return (
    // The wrapper carries the hint: a disabled button gets no pointer events of its own.
    <span title={disabledReason ?? undefined} className="inline-flex">
      <Button size="sm" onClick={onStart} disabled={!canStart}>
        {isStarting ? <Loader2 className="size-4 animate-spin" /> : null}
        Generate next round
      </Button>
    </span>
  );
}

/** One line under the header while a round generates, and its outcome once it ends. */
export function RoundProgressStrip({
  roundId,
  round,
  error,
  onDismiss,
}: {
  roundId: number | null;
  round: GenerationRound | null;
  error: string | null;
  onDismiss: () => void;
}) {
  if (roundId == null) return null;

  const active = round ? round.status === "queued" || round.status === "running" : !error;
  const settled = round ? round.produced + round.dropped : 0;
  const tone =
    error || round?.status === "failed" ? "critical" : round?.status === "done" ? "ok" : "muted";

  let message: string;
  if (error) {
    message = `Could not read round progress: ${error}`;
  } else if (!round) {
    message = "Loading round progress...";
  } else if (round.status === "queued") {
    message = `Round ${round.number} queued: ${round.requested} questions requested`;
  } else if (round.status === "running") {
    message = `Generating round ${round.number}: produced ${round.produced}, dropped ${round.dropped} of ${round.requested}`;
  } else if (round.status === "done") {
    message = `Round ${round.number} done: produced ${round.produced}, dropped ${round.dropped} of ${round.requested}. New questions are in the queue.`;
  } else {
    message = `Round ${round.number} failed${round.error ? `: ${round.error}` : "."}`;
  }

  return (
    <div
      role="status"
      className="review-banner items-center py-2.5"
      data-tone={tone}
      data-testid="round-progress"
    >
      {active ? (
        <Loader2 className="size-4 shrink-0 animate-spin text-[var(--review-muted)]" />
      ) : null}
      <div className="min-w-0 grow space-y-2">
        <p className="review-banner-copy">{message}</p>
        {round && active ? (
          <Progress
            value={round.requested ? (settled / round.requested) * 100 : 0}
            className="review-progress h-1"
          />
        ) : null}
      </div>
      {!active ? (
        <Button
          variant="ghost"
          size="icon"
          className="size-7"
          aria-label="Dismiss round status"
          onClick={onDismiss}
        >
          <X className="size-4" />
        </Button>
      ) : null}
    </div>
  );
}
