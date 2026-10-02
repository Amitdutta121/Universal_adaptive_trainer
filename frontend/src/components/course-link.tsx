"use client";

/**
 * A `next/link` whose `href` is relative to the open course: `<CourseLink
 * href="/books/3">` goes to `/courses/{id}/books/3`. Only for screens under
 * `/courses/[courseId]`; links that leave the course use `Link` directly.
 */

import Link from "next/link";
import type { ComponentProps } from "react";
import { useCoursePath } from "@/lib/use-course";

export function CourseLink({
  href,
  ...props
}: Omit<ComponentProps<typeof Link>, "href"> & { href: string }) {
  const toCourse = useCoursePath();
  return <Link href={toCourse(href)} {...props} />;
}
