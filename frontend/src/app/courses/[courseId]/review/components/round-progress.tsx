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

function counts(round: GenerationRound): string {
  const skipped = round.skipped ?? 0;
  const skip = skipped > 0 ? `, skipped ${skipped}` : "";
  return `produced ${round.produced}, dropped ${round.dropped}${skip} of ${round.requested}`;
}

/** What the round's lesson run learned from the reviews before it generated (ADR-063). */
function lessons(round: GenerationRound): string {
  const applied = round.lessons_applied ?? 0;
  const parts = [
    applied > 0 ? `Applied lessons from ${applied} review${applied === 1 ? "" : "s"}.` : "",
    round.lessons_error ? `Some lessons were not applied: ${round.lessons_error}` : "",
  ];
  return parts.filter(Boolean).join(" ");
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
  const settled = round ? round.produced + round.dropped + (round.skipped ?? 0) : 0;
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
    const learned = lessons(round);
    message = `Generating round ${round.number}: ${counts(round)}${learned ? `. ${learned}` : ""}`;
  } else if (round.status === "done") {
    const why = round.skip_reason ? ` ${round.skip_reason}` : "";
    const learned = lessons(round);
    message = `Round ${round.number} done: ${counts(round)}.${why} New questions are in the queue.${learned ? ` ${learned}` : ""}`;
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
