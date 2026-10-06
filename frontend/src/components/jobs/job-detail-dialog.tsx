"use client";

/**
 * The run window: every job of the course on the left, the selected one on the right.
 *
 * Opened by `?job=<id>` (a row of the Jobs popover, a toast's "View", a link) or
 * `?job=all` ("View all jobs", which selects the first job still running). On a
 * narrow screen it shows the list, then the job with a way back.
 */

import { ChevronLeft } from "lucide-react";
import { useEffect, useState } from "react";
import { CourseLink } from "@/components/course-link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import type { Job } from "@/lib/api/types";
import { formatDuration, timeAgo } from "@/lib/display";
import { cn } from "@/lib/utils";
import {
  isActive,
  type JobFilter,
  KIND_LABEL,
  linkLabel,
  matchesFilter,
  outcomeText,
  progressPercent,
  progressText,
  STATUS_LABEL,
} from "./job-display";
import { JobActions } from "./job-actions";
import { JobStatusIcon } from "./job-status-icon";

const FILTERS: ReadonlyArray<{ value: JobFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "active", label: "Active" },
  { value: "done", label: "Done" },
  { value: "failed", label: "Failed" },
];

const STATUS_BADGE: Record<Job["status"], string> = {
  running: "bg-primary/10 text-primary",
  queued: "bg-muted text-muted-foreground",
  done: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  failed: "bg-destructive/10 text-destructive",
  cancelled: "bg-muted text-muted-foreground",
};

export function JobDetailDialog({
  jobs,
  jobParam,
  onSelect,
  onClose,
}: {
  jobs: readonly Job[];
  /** `?job=`: a job id, `"all"`, or `null` when the window is closed. */
  jobParam: string | null;
  onSelect: (jobId: string) => void;
  onClose: () => void;
}) {
  const [filter, setFilter] = useState<JobFilter>("all");
  // "View all" lands on the first job still running, so the right side is not empty.
  // On a phone the list comes first instead (`md:` below shows both side by side).
  const selectedId =
    jobParam === "all" ? (jobs.find(isActive) ?? jobs[0])?.id ?? null : jobParam;
  const selected = jobs.find((job) => job.id === selectedId) ?? null;
  const [showList, setShowList] = useState(jobParam === "all");

  useEffect(() => {
    if (jobParam === null) setFilter("all");
    setShowList(jobParam === "all");
  }, [jobParam]);

  const listed = jobs.filter((job) => matchesFilter(job, filter));
  const count = (value: JobFilter) => jobs.filter((job) => matchesFilter(job, value)).length;

  return (
    <Dialog open={jobParam !== null} onOpenChange={(open) => (open ? null : onClose())}>
      <DialogContent className="grid h-[min(46rem,calc(100dvh-4rem))] max-w-[calc(100%-2rem)] grid-cols-1 gap-0 overflow-hidden p-0 sm:max-w-5xl md:grid-cols-[20rem_1fr]">
        <DialogTitle className="sr-only">Jobs</DialogTitle>
        <DialogDescription className="sr-only">
          Generation runs, question rounds and judge runs of this course.
        </DialogDescription>

        <aside
          className={cn(
            "flex min-h-0 flex-col border-r bg-muted/30",
            selected && !showList ? "hidden md:flex" : "flex",
          )}
        >
          <div className="space-y-2.5 border-b px-4 pt-4 pb-3">
            <h2 className="font-heading font-semibold text-base">Jobs</h2>
            <div className="grid grid-cols-4 gap-0.5 rounded-lg bg-muted p-0.5" role="tablist">
              {FILTERS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  role="tab"
                  aria-selected={filter === option.value}
                  onClick={() => setFilter(option.value)}
                  className={cn(
                    "rounded-md px-1.5 py-1 text-xs",
                    filter === option.value
                      ? "bg-background font-medium text-foreground shadow-xs"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {option.label}
                  <span className="ml-1 text-muted-foreground tabular-nums">
                    {count(option.value)}
                  </span>
                </button>
              ))}
            </div>
          </div>
          <ul className="min-h-0 flex-1 overflow-y-auto">
            {listed.length === 0 ? (
              <li className="px-4 py-6 text-muted-foreground text-sm">Nothing here.</li>
            ) : (
              listed.map((job) => (
                <li key={job.id}>
                  <button
                    type="button"
                    onClick={() => {
                      setShowList(false);
                      onSelect(job.id);
                    }}
                    aria-current={job.id === selected?.id}
                    className={cn(
                      "grid w-full grid-cols-[1rem_1fr] gap-2.5 border-b px-4 py-2.5 text-left hover:bg-muted/60",
                      job.id === selected?.id && "bg-background",
                    )}
                  >
                    <JobStatusIcon status={job.status} className="mt-0.5" />
                    <span className="min-w-0">
                      <span
                        className={cn(
                          "block truncate font-medium text-sm",
                          job.id === selected?.id && "text-primary",
                        )}
                      >
                        {job.title}
                      </span>
                      <span className="block truncate text-muted-foreground text-xs">
                        {KIND_LABEL[job.kind]} ·{" "}
                        {isActive(job)
                          ? STATUS_LABEL[job.status].toLowerCase()
                          : timeAgo(job.finished_at ?? job.created_at)}
                      </span>
                    </span>
                  </button>
                </li>
              ))
            )}
          </ul>
        </aside>

        <section
          className={cn(
            "min-h-0 overflow-y-auto px-6 py-5 md:px-7",
            selected && !showList ? "block" : "hidden md:block",
          )}
        >
          {selected ? (
            <JobDetail
              job={selected}
              onBack={() => setShowList(true)}
              onRetried={(newJobId) => onSelect(newJobId)}
            />
          ) : (
            <p className="py-10 text-center text-muted-foreground text-sm">
              Nothing has run in this course yet.
            </p>
          )}
        </section>
      </DialogContent>
    </Dialog>
  );
}

function JobDetail({
  job,
  onBack,
  onRetried,
}: {
  job: Job;
  onBack: () => void;
  onRetried: (newJobId: string) => void;
}) {
  return (
    <div className="space-y-5">
      <div className="space-y-1.5 pr-8">
        <Button
          variant="link"
          size="sm"
          className="-ml-1 h-auto p-0 text-xs md:hidden"
          onClick={onBack}
        >
          <ChevronLeft className="size-3.5" /> All jobs
        </Button>
        <p className="font-mono text-[0.65rem] text-muted-foreground uppercase tracking-[0.12em]">
          {KIND_LABEL[job.kind]}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-heading font-semibold text-xl tracking-[-0.02em]">{job.title}</h3>
          <Badge className={cn("border-transparent", STATUS_BADGE[job.status])}>
            {STATUS_LABEL[job.status]}
          </Badge>
        </div>
      </div>

      <dl className="flex flex-wrap gap-x-8 gap-y-3 text-sm">
        <Fact label="Started">{job.started_at ? timeAgo(job.started_at) : "Not yet"}</Fact>
        <Fact label="Duration">
          <span className="font-mono text-xs">
            {job.started_at ? formatDuration(job.started_at, job.finished_at) : "—"}
          </span>
        </Fact>
        <Fact label="Progress">{progressText(job)}</Fact>
        {!isActive(job) ? <Fact label="Outcome">{outcomeText(job)}</Fact> : null}
      </dl>

      {isActive(job) ? <Progress value={progressPercent(job)} className="h-1.5" /> : null}

      <JobActions job={job} onRetried={onRetried} />

      {job.error ? (
        <p
          className={cn(
            "rounded-lg px-3 py-2 text-sm",
            job.status === "cancelled"
              ? "bg-muted text-muted-foreground"
              : "bg-destructive/10 text-destructive",
          )}
        >
          {job.error}
        </p>
      ) : null}

      <JobCounts job={job} />

      {/* A run that failed before making anything has nothing to open. */}
      {job.link && !((job.status === "failed" || job.status === "cancelled") && job.done === 0) ? (
        <CourseLink
          href={job.link}
          className="inline-block font-medium text-primary text-sm underline-offset-4 hover:underline"
        >
          {linkLabel(job)} →
        </CourseLink>
      ) : null}
    </div>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

/** The kind's own breakdown — what a round dropped, what a coverage fill skipped. */
function JobCounts({ job }: { job: Job }) {
  const rows: Array<[string, number]> = [];
  const result = job.result;
  if (result && "generated" in result) {
    rows.push(["Generated", result.generated.length]);
    rows.push(["Skipped (no confident section)", result.skipped.length]);
    rows.push(["Failed", result.failed.length]);
    rows.push(["Possible duplicates", result.possible_duplicates]);
  } else if (result && "created" in result) {
    rows.push(["Planned", result.planned.length]);
    rows.push(["Generated", result.created]);
    rows.push([
      "Failed validation",
      result.questions.filter((question) => question.validation_passed === false).length,
    ]);
  } else {
    for (const [name, value] of Object.entries(job.counts ?? {})) {
      rows.push([name.charAt(0).toUpperCase() + name.slice(1), value]);
    }
  }
  if (rows.length === 0) return null;
  return (
    <dl className="divide-y rounded-lg border text-sm">
      {rows.map(([name, value]) => (
        <div key={name} className="flex items-center justify-between px-3.5 py-2.5">
          <dt>{name}</dt>
          <dd className="font-mono text-muted-foreground text-xs tabular-nums">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
