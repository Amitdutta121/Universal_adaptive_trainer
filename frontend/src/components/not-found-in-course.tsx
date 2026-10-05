"use client";

/**
 * What a page inside a course shows when the row in its URL is not in that course: the
 * course's `not-found.tsx` for server-rendered pages, and client screens on a 404.
 *
 * The API answers the same 404 for a row that does not exist and for one that belongs to
 * another course (ADR-058), so this cannot tell the two apart and does not try.
 */

import { SearchX } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { courseIdFromPath, coursePath } from "@/lib/course";

export function NotFoundInCourse() {
  const courseId = courseIdFromPath(usePathname());

  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-2 py-12 text-center">
        <span className="grid size-10 place-items-center rounded-full bg-muted text-muted-foreground">
          <SearchX className="size-5" />
        </span>
        <h1 className="font-semibold">Not found in this course</h1>
        <p className="max-w-md text-muted-foreground text-sm">
          Nothing at this link belongs to this course. It may have been deleted, or the link points
          at another course.
        </p>
        {courseId !== null ? (
          <Button asChild size="sm" className="mt-2">
            <Link href={coursePath(courseId, "/dashboard")}>Back to the course</Link>
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}
