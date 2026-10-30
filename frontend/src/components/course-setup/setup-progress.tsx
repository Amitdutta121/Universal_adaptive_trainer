"use client";

/**
 * The sidebar's reminder of course setup: "Course setup 3/6 · Next: …", on every course page
 * until students can join, linking back to the checklist on the dashboard.
 */

import Link from "next/link";
import { coursePath } from "@/lib/course";
import { useCourseSetup } from "@/lib/course-setup";

export function SetupProgress({ courseId }: { courseId: number }) {
  const { setup } = useCourseSetup(courseId);
  if (!setup || setup.live) return null;
  return (
    <Link
      href={coursePath(courseId, "/dashboard")}
      className="mx-2 grid gap-1.5 rounded-lg border bg-background px-3 py-2 text-xs hover:border-primary/40 group-data-[collapsible=icon]:hidden"
      data-testid="setup-progress"
    >
      <span className="flex justify-between font-medium">
        <span>Course setup</span>
        <span className="tabular-nums">
          {setup.done}/{setup.total}
        </span>
      </span>
      <span className="h-1 overflow-hidden rounded-full bg-muted">
        <span
          className="block h-full bg-primary"
          style={{ width: `${(setup.done / setup.total) * 100}%` }}
        />
      </span>
      {setup.next ? (
        <span className="truncate text-muted-foreground">Next: {setup.next.title}</span>
      ) : null}
    </Link>
  );
}
