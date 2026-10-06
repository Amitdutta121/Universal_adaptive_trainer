"use client";

/**
 * Where the sheet's last run is, read from its background job.
 *
 * The run keeps going after this page is left or the tab is closed, so this is a
 * view onto the Jobs list rather than the request's own result: queued or running
 * shows progress, done shows what it produced (`RunResults`), failed shows why and
 * what was kept.
 */

import { CircleAlert, LoaderCircle } from "lucide-react";
import { parseAsString, useQueryState } from "nuqs";
import { CourseLink } from "@/components/course-link";
import { JobActions } from "@/components/jobs/job-actions";
import { progressPercent } from "@/components/jobs/job-display";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import type { Job } from "@/lib/api/types";
import { pluralise } from "@/lib/display";
import { RunResults } from "./run-results";

export function RunJobStatus({
  job,
  onRetried,
}: {
  job: Job;
  /** A retry starts a new job; the screen follows that one instead. */
  onRetried: (newJobId: string) => void;
}) {
  const [, setJobParam] = useQueryState("job", parseAsString);
  const openInJobs = (
    <Button
      variant="link"
      size="sm"
      className="h-auto p-0 text-xs"
      onClick={() => void setJobParam(job.id)}
    >
      Open in Jobs →
    </Button>
  );

  if (job.status === "done" && job.result && "created" in job.result) {
    return <RunResults result={job.result} />;
  }

  if (job.status === "failed" || job.status === "cancelled") {
    const cancelled = job.status === "cancelled";
    return (
      <Alert variant={cancelled ? "default" : "destructive"}>
        <CircleAlert />
        <AlertTitle>
          {cancelled ? "You stopped the run" : "The run stopped"} after{" "}
          {pluralise(job.done, "question")}
        </AlertTitle>
        <AlertDescription className="space-y-1.5">
          <p>{job.error}</p>
          {job.done > 0 ? (
            <p>Every question made before it stopped is saved and reviewable.</p>
          ) : null}
          <JobActions job={job} onRetried={onRetried} />
          <div className="flex gap-4">
            {job.link && job.done > 0 ? (
              <CourseLink href={job.link} className="font-medium text-xs underline">
                Open these questions →
              </CourseLink>
            ) : null}
            {openInJobs}
          </div>
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <Alert className="border-primary/40">
      <LoaderCircle className="animate-spin" />
      <AlertTitle>
        {job.status === "queued" ? "Starting the run…" : `Generating ${job.done} of ${job.total}`}
      </AlertTitle>
      <AlertDescription className="space-y-2">
        <Progress value={progressPercent(job)} className="h-1.5" />
        <p>
          It runs in the background — you can leave this page or close the tab. Questions are saved
          one at a time, and you will be told when it finishes.
        </p>
        <JobActions job={job} onRetried={onRetried} />
        {openInJobs}
      </AlertDescription>
    </Alert>
  );
}
