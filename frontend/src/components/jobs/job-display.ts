/**
 * Wording and arithmetic shared by the Jobs button, popover and run window.
 *
 * Pure, so every place that shows a job says the same thing about it.
 */

import type { Job } from "@/lib/api/types";
import { pluralise, timeAgo } from "@/lib/display";

export type JobStatus = Job["status"];

export const KIND_LABEL: Record<Job["kind"], string> = {
  bulk_generation: "Bulk generation",
  coverage_fill: "Coverage fill",
  book_import: "Book import",
  question_round: "Question round",
  judge_run: "Judge run",
};

export const STATUS_LABEL: Record<JobStatus, string> = {
  queued: "Queued",
  running: "Running",
  done: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

/** What the run window's tabs filter on. */
export type JobFilter = "all" | "active" | "done" | "failed";

export function isActive(job: Job): boolean {
  return job.status === "queued" || job.status === "running";
}

export function matchesFilter(job: Job, filter: JobFilter): boolean {
  if (filter === "all") return true;
  if (filter === "active") return isActive(job);
  // A cancelled job is listed with the failures: both stopped short of what was asked.
  if (filter === "failed") return job.status === "failed" || job.status === "cancelled";
  return job.status === filter;
}

/** 0–100. A finished job is full whatever its counters say. */
export function progressPercent(job: Job): number {
  if (job.status === "done") return 100;
  if (job.total <= 0) return 0;
  return Math.min(100, Math.round((job.done / job.total) * 100));
}

/** "18 / 40" — the unit is in the title, so the counter stays short. */
export function progressText(job: Job): string {
  return `${job.done} / ${job.total}`;
}

/** The one line under a job's title: where it is now, or how it ended. */
export function jobSubline(job: Job, now?: number): string {
  if (job.status === "queued") return "Waiting to start";
  if (job.status === "running") {
    if (job.cancel_requested) return "Stopping after the current question…";
    const since = job.started_at ? ` · started ${timeAgo(job.started_at, now)}` : "";
    return `${progressText(job)}${since}`;
  }
  const when = job.finished_at ? ` · ${timeAgo(job.finished_at, now)}` : "";
  if (job.status === "failed" || job.status === "cancelled") {
    return `${job.error ?? STATUS_LABEL[job.status]}${when}`;
  }
  return `${outcomeText(job)}${when}`;
}

/** How a finished job ended, in its own terms. */
export function outcomeText(job: Job): string {
  const counts = job.counts ?? {};
  switch (job.kind) {
    case "question_round":
      return [
        pluralise(counts.made ?? 0, "question"),
        counts.dropped ? `${counts.dropped} dropped` : null,
        counts.skipped ? `${counts.skipped} skipped` : null,
      ]
        .filter(Boolean)
        .join(" · ");
    case "judge_run":
      return [
        pluralise(counts.judged ?? 0, "question") + " judged",
        counts.failed ? `${counts.failed} failed` : null,
      ]
        .filter(Boolean)
        .join(" · ");
    case "book_import": {
      const result = job.result;
      if (!result || !("book" in result)) return "Imported";
      const { book } = result;
      return book.status === "partial"
        ? `Imported “${book.title}” (partial)`
        : `Imported “${book.title}”`;
    }
    case "coverage_fill": {
      // `done` counts gap cells handled; a skipped cell made no question.
      const result = job.result;
      const made = result && "generated" in result ? result.generated.length : job.done;
      return pluralise(made, "question");
    }
    default: {
      const result = job.result;
      return pluralise(result && "created" in result ? result.created : job.done, "question");
    }
  }
}

/** Where the job's output can be looked at, in words, for its link. */
export function linkLabel(job: Job): string {
  switch (job.kind) {
    case "question_round":
      return "Open in review";
    case "judge_run":
      return "Open judges";
    case "book_import":
      return "Open book";
    default:
      return "Open these questions";
  }
}
