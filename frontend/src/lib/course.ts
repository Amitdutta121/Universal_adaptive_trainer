/**
 * The course a professor screen works inside.
 *
 * Every professor screen lives under `/courses/[courseId]/…`, so the URL is the
 * one source of truth for which course is open: a link can be shared, two tabs
 * can hold two courses, and nothing has to be remembered between visits. The API
 * client reads the same segment to send `X-Course-Id` (see `api/client.ts`).
 *
 * Server-safe on purpose: Server Components call `coursePath`. The hooks that
 * read the URL live in `use-course.ts`, which is a client module.
 */

import type { Route } from "next";

const COURSE_SEGMENT = /^\/courses\/(\d+)(?:\/|$)/;

/** The course id in a pathname, or `null` outside a course. */
export function courseIdFromPath(pathname: string): number | null {
  const match = COURSE_SEGMENT.exec(pathname);
  return match ? Number(match[1]) : null;
}

/** The absolute path of `path` (e.g. `/books/3`) inside course `courseId`. */
export function coursePath(courseId: number | string, path: string): Route {
  return `/courses/${courseId}${path === "/" ? "" : path}` as Route;
}
