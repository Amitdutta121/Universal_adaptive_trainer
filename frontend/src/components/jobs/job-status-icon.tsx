import { CircleAlert, CircleCheck, CircleSlash, Clock, LoaderCircle } from "lucide-react";
import type { Job } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/** One icon per job status, used wherever a job is listed. */
export function JobStatusIcon({ status, className }: { status: Job["status"]; className?: string }) {
  const base = cn("size-4 shrink-0", className);
  switch (status) {
    case "running":
      return <LoaderCircle aria-hidden className={cn(base, "animate-spin text-primary")} />;
    case "queued":
      return <Clock aria-hidden className={cn(base, "text-muted-foreground")} />;
    case "done":
      return <CircleCheck aria-hidden className={cn(base, "text-emerald-600 dark:text-emerald-400")} />;
    case "failed":
      return <CircleAlert aria-hidden className={cn(base, "text-destructive")} />;
    case "cancelled":
      return <CircleSlash aria-hidden className={cn(base, "text-muted-foreground")} />;
  }
}
