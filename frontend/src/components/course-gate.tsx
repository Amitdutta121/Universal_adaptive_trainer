"use client";

/**
 * Renders a course's screens only once the backend confirms the professor owns it.
 *
 * The API answers 404 for a course that does not exist and for one another
 * professor owns (ADR-058), so a stale or shared link lands here instead of on a
 * screen whose every request fails. Outside a course this renders its children.
 */

import { FolderX } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { QueryError } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { readApiError } from "@/lib/api/client";
import { useCourse } from "@/lib/api/queries";
import { courseIdFromPath } from "@/lib/course";

export function CourseGate({ children }: { children: React.ReactNode }) {
  const courseId = courseIdFromPath(usePathname());
  const course = useCourse(courseId);

  if (courseId === null || course.isSuccess) return <>{children}</>;
  if (course.isError) {
    return readApiError(course.error)?.status === 404 ? (
      <CourseNotFound courseId={courseId} />
    ) : (
      <QueryError error={course.error} />
    );
  }
  // Loading: render nothing rather than a screen that may be about to be refused.
  return null;
}

export function CourseNotFound({ courseId }: { courseId: number }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-2 py-12 text-center">
        <span className="grid size-10 place-items-center rounded-full bg-muted text-muted-foreground">
          <FolderX className="size-5" />
        </span>
        <h1 className="font-semibold">Course not found</h1>
        <p className="max-w-md text-muted-foreground text-sm">
          None of your courses has id {courseId}. The link may be out of date, or the course
          belongs to another professor.
        </p>
        <Button asChild size="sm" className="mt-2">
          <Link href={"/courses" as Route}>Back to your courses</Link>
        </Button>
      </CardContent>
    </Card>
  );
}
