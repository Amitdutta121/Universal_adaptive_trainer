"use client";

/**
 * Cancel and Retry for one job.
 *
 * The server decides whether a job can be cancelled (`can_cancel`) and what retrying it
 * would start (`retry_label`, e.g. "Retry the remaining 14"); this only offers what it says.
 * Retry starts a *new* job, which `onRetried` is handed so the caller can follow it.
 */

import { RotateCcw, Square } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { useCancelJob, useRetryJob } from "@/lib/api/queries";
import type { Job } from "@/lib/api/types";
import { isActive } from "./job-display";

function describe(error: unknown): string | undefined {
  if (error instanceof ApiError) return error.detail ?? error.message;
  return error instanceof Error ? error.message : undefined;
}

export function JobActions({
  job,
  onRetried,
}: {
  job: Job;
  onRetried?: (newJobId: string) => void;
}) {
  const cancel = useCancelJob();
  const retry = useRetryJob();

  async function stop() {
    try {
      await cancel.mutateAsync(job.id);
    } catch (error) {
      toast.error("Could not cancel the job", { description: describe(error) });
    }
  }

  async function again() {
    try {
      const started = await retry.mutateAsync(job.id);
      toast.success("Retry started", { description: job.retry_label ?? undefined });
      onRetried?.(started.job_id);
    } catch (error) {
      toast.error("Could not retry the job", { description: describe(error) });
    }
  }

  const stopping = isActive(job) && job.cancel_requested;
  const unstoppable = isActive(job) && job.kind === "judge_run";
  if (!job.can_cancel && !job.retry_label && !stopping && !unstoppable) return null;

  return (
    <div className="flex flex-wrap items-center gap-2">
      {job.can_cancel ? (
        <Button
          variant="outline"
          size="sm"
          className="text-destructive"
          disabled={cancel.isPending}
          onClick={() => void stop()}
        >
          <Square className="size-3.5" /> {cancel.isPending ? "Cancelling…" : "Cancel"}
        </Button>
      ) : null}
      {stopping ? (
        <span className="text-muted-foreground text-xs">
          Stopping after the current question. Everything made so far is kept.
        </span>
      ) : null}
      {unstoppable ? (
        <span className="text-muted-foreground text-xs">
          A judge run can&apos;t be stopped once it is submitted; its results arrive here.
        </span>
      ) : null}
      {job.retry_label ? (
        <Button size="sm" disabled={retry.isPending} onClick={() => void again()}>
          <RotateCcw className="size-3.5" /> {retry.isPending ? "Starting…" : job.retry_label}
        </Button>
      ) : null}
    </div>
  );
}
