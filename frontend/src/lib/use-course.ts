"use client";

/** Hooks for screens under `/courses/[courseId]`; see `lib/course.ts` for the rules. */

import type { Route } from "next";
import { useParams } from "next/navigation";
import { useCallback } from "react";
import { coursePath } from "./course";

/** The open course's id. Only call from a screen under `/courses/[courseId]`. */
export function useCourseId(): number {
  const params = useParams<{ courseId?: string }>();
  const id = Number(params?.courseId);
  if (!Number.isInteger(id)) {
    throw new Error("useCourseId() was called outside /courses/[courseId].");
  }
  return id;
}

/** `href` builder for links that stay inside the open course. */
export function useCoursePath(): (path: string) => Route {
  const courseId = useCourseId();
  return useCallback((path: string) => coursePath(courseId, path), [courseId]);
}
