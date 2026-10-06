"use client";

/**
 * The header's Jobs button: how many jobs are running, a popover with what is in
 * progress and what just finished, and the way into the run window.
 *
 * Clicking a job or "View all jobs" sets `?job=` in the URL, which opens
 * `JobDetailDialog` — so a job can be linked, and the back button closes it.
 * This component also notices a job finishing (see `useJobFinishedToasts`), since
 * it is mounted on every professor page of a course.
 */

import { ListTodo, LoaderCircle } from "lucide-react";
import { usePathname } from "next/navigation";
import { parseAsString, useQueryState } from "nuqs";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Progress } from "@/components/ui/progress";
import { useJobs } from "@/lib/api/queries";
import type { Job } from "@/lib/api/types";
import { courseIdFromPath } from "@/lib/course";
import { cn } from "@/lib/utils";
import { isActive, jobSubline, progressPercent } from "./job-display";
import { JobDetailDialog } from "./job-detail-dialog";
import { JobStatusIcon } from "./job-status-icon";
import { useJobFinishedToasts } from "./use-job-finished-toasts";

/** Finished jobs the popover shows under "Recently finished"; the rest are in the window. */
const RECENT_FINISHED = 3;

/** The Jobs button for the page header: inside a course only, since jobs belong to one. */
export function HeaderJobs() {
  const pathname = usePathname();
  return courseIdFromPath(pathname ?? "") === null ? null : <JobsMenu />;
}

export function JobsMenu() {
  const jobs = useJobs();
  const [open, setOpen] = useState(false);
  const [jobParam, setJobParam] = useQueryState("job", parseAsString);
  const all = jobs.data?.jobs ?? [];
  useJobFinishedToasts(all, (jobId) => void setJobParam(jobId));

  const active = all.filter(isActive);
  const running = active.filter((job) => job.status === "running").length;
  const queued = active.length - running;
  const finished = all.filter((job) => !isActive(job)).slice(0, RECENT_FINISHED);

  const openJob = (jobId: string) => {
    setOpen(false);
    void setJobParam(jobId);
  };

  return (
    <>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button variant="outline" size="sm" className="h-9 gap-2">
            {running > 0 ? (
              <LoaderCircle className="size-4 animate-spin text-primary" />
            ) : (
              <ListTodo className="size-4" />
            )}
            Jobs
            {running > 0 ? (
              <span className="inline-grid h-[18px] min-w-[18px] place-items-center rounded-full bg-primary px-1.5 font-semibold text-[11px] text-primary-foreground tabular-nums">
                {running}
              </span>
            ) : null}
          </Button>
        </PopoverTrigger>
        <PopoverContent align="end" className="w-[26rem] max-w-[calc(100vw-2rem)] p-0">
          <div className="flex items-center justify-between border-b px-3.5 py-2.5">
            <span className="font-heading font-semibold text-sm">Jobs</span>
            <span className="text-muted-foreground text-xs">
              {running} running · {queued} queued
            </span>
          </div>
          <div className="max-h-[26rem] overflow-y-auto pb-1">
            {jobs.isPending ? (
              <p className="px-3.5 py-6 text-center text-muted-foreground text-sm">Loading…</p>
            ) : jobs.isError ? (
              <p className="px-3.5 py-6 text-center text-destructive text-sm">
                Could not load jobs.
              </p>
            ) : all.length === 0 ? (
              <p className="px-3.5 py-6 text-center text-muted-foreground text-sm">
                Nothing has run in this course yet. Generation runs, question rounds and judge runs
                show up here.
              </p>
            ) : (
              <>
                <GroupLabel>{active.length > 0 ? "In progress" : "Nothing running"}</GroupLabel>
                {active.map((job) => (
                  <JobRow key={job.id} job={job} onOpen={openJob} />
                ))}
                {finished.length > 0 ? <GroupLabel>Recently finished</GroupLabel> : null}
                {finished.map((job) => (
                  <JobRow key={job.id} job={job} onOpen={openJob} />
                ))}
              </>
            )}
          </div>
          <div className="flex justify-end border-t px-3.5 py-2">
            <Button
              variant="link"
              size="sm"
              className="h-auto p-0 text-xs"
              onClick={() => openJob("all")}
            >
              View all jobs →
            </Button>
          </div>
        </PopoverContent>
      </Popover>
      <JobDetailDialog
        jobs={all}
        jobParam={jobParam}
        onSelect={(jobId) => void setJobParam(jobId)}
        onClose={() => void setJobParam(null)}
      />
    </>
  );
}

function GroupLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="px-3.5 pt-2.5 pb-1 font-mono text-[0.65rem] text-muted-foreground uppercase tracking-[0.12em]">
      {children}
    </p>
  );
}

function JobRow({ job, onOpen }: { job: Job; onOpen: (jobId: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(job.id)}
      className="grid w-full grid-cols-[1rem_1fr] gap-2.5 px-3.5 py-2 text-left hover:bg-muted/60 focus-visible:bg-muted/60 focus-visible:outline-none"
    >
      <JobStatusIcon status={job.status} className="mt-0.5" />
      <span className="min-w-0">
        <span className="block truncate font-medium text-sm">{job.title}</span>
        <span
          className={cn(
            "block truncate text-xs",
            job.status === "failed" ? "text-destructive" : "text-muted-foreground",
          )}
        >
          {jobSubline(job)}
        </span>
        {job.status === "running" ? (
          <Progress value={progressPercent(job)} className="mt-1.5 h-1" />
        ) : null}
      </span>
    </button>
  );
}
