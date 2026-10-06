"use client";

/**
 * Tell the professor when a job they started finishes, wherever they are in the course.
 *
 * Watches the Jobs list for a job that was queued or running and now is not. That
 * job's output just landed, so the lists it changes are refetched here: the screen
 * that started it may be long gone, and nothing else would notice.
 */

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { toast } from "sonner";
import { qk } from "@/lib/api/queries";
import type { Job } from "@/lib/api/types";
import { isActive, outcomeText } from "./job-display";

export function useJobFinishedToasts(jobs: readonly Job[], onView: (jobId: string) => void) {
  const client = useQueryClient();
  // Status per job id at the previous refetch. `null` until the first list arrives, so
  // jobs that were already finished on page load are not announced.
  const previous = useRef<Map<string, Job["status"]> | null>(null);
  const viewRef = useRef(onView);
  viewRef.current = onView;

  useEffect(() => {
    const before = previous.current;
    previous.current = new Map(jobs.map((job) => [job.id, job.status]));
    if (before === null) return;

    const finished = jobs.filter((job) => {
      const was = before.get(job.id);
      return (was === "queued" || was === "running") && !isActive(job);
    });
    if (finished.length === 0) return;

    for (const key of [
      qk.questions.all,
      qk.system.counts(),
      qk.coverage.all,
      qk.rounds.all,
      qk.setup.all,
      qk.evaluation.all,
    ]) {
      client.invalidateQueries({ queryKey: key });
    }
    for (const job of finished) {
      const action = { label: "View", onClick: () => viewRef.current(job.id) };
      if (job.status === "cancelled") {
        toast.message(`${job.title} cancelled`, { description: job.error ?? undefined, action });
      } else if (job.status === "failed") {
        toast.error(`${job.title} failed`, { description: job.error ?? undefined, action });
      } else {
        toast.success(`${job.title} finished`, { description: outcomeText(job), action });
      }
    }
  }, [jobs, client]);
}
