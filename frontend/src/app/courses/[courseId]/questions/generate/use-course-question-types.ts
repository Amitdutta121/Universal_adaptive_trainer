"use client";

/**
 * The question types this course chose when it was created (ADR-054), in canonical order.
 *
 * Every generate screen offers only these, and the backend refuses any other type for the
 * course, so the two agree. While the course is loading this returns every type, so the screens
 * render rather than flash empty; the backend check still applies.
 */

import { useMemo } from "react";
import { useCourse } from "@/lib/api/queries";
import type { QuestionType } from "@/lib/api/types";
import { useCourseId } from "@/lib/use-course";
import { QUESTION_TYPES } from "./spec-sheet-types";

export function useCourseQuestionTypes(): readonly QuestionType[] {
  const course = useCourse(useCourseId());
  const chosen = course.data?.question_types;
  return useMemo(
    () => (chosen ? QUESTION_TYPES.filter((type) => chosen.includes(type)) : QUESTION_TYPES),
    [chosen],
  );
}
