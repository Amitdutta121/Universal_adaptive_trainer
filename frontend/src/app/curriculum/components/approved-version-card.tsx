"use client";

/**
 * Which taxonomy the platform is actually grounded in.
 *
 * The versions table lists history; this says which row of it is live. That is
 * the one fact a professor needs before generating anything, so it is stated
 * rather than left to be inferred from a badge in a list.
 *
 * Having no approved version is a blocking condition, not an empty space:
 * generation is refused until one exists, so the absence is rendered as an alert
 * that says so. `GET /api/curriculum/approved` answers 404 in that case, which is
 * a state, not a failure.
 */

import { CircleCheck, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { QueryError } from "@/components/query-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import type { CurriculumVersionDetail } from "@/lib/api/types";
import { formatTimestamp, pluralise } from "@/lib/display";

export function ApprovedVersionCard({
  approved,
  isPending,
  error,
}: {
  approved: CurriculumVersionDetail | undefined;
  isPending: boolean;
  error: unknown;
}) {
  if (isPending) return <Skeleton className="h-[5rem] w-full" />;

  // A 404 means nothing has been uploaded yet, which the professor needs told
  // plainly. Any other error is the API failing and is shown as one.
  if (error) {
    if (!(error instanceof ApiError && error.status === 404)) return <QueryError error={error} />;
    return (
      <Alert>
        <TriangleAlert />
        <AlertTitle>No curriculum has been approved yet</AlertTitle>
        <AlertDescription>
          Question generation is refused until a valid taxonomy is uploaded. Upload one above.
        </AlertDescription>
      </Alert>
    );
  }

  if (!approved) return null;

  return (
    <Alert>
      <CircleCheck />
      <AlertTitle>
        <Link href={`/curriculum/versions/${approved.version.id}`} className="hover:underline">
          {approved.version.label}
        </Link>{" "}
        is the approved curriculum
      </AlertTitle>
      <AlertDescription>
        <p>
          {pluralise(approved.topic_count, "topic")} ·{" "}
          {pluralise(approved.subtopic_count, "subtopic")}
          {approved.version.approved_at
            ? ` · approved ${formatTimestamp(approved.version.approved_at)}`
            : ""}
        </p>
        <p>Question generation and coverage are both grounded in this version.</p>
      </AlertDescription>
    </Alert>
  );
}
