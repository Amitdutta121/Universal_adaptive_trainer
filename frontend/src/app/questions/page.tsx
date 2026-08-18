/**
 * The questions route shell.
 *
 * `QuestionsBrowser` keeps its filters in the URL, which means it reads search
 * params, which Next requires to sit inside a Suspense boundary — without one the
 * whole route opts out of static rendering at build time. The boundary lives here
 * so the browser component stays about questions.
 */

import { Suspense } from "react";
import { PageHeader } from "@/components/page-header";
import { TableSkeleton } from "@/components/query-state";
import { QuestionsBrowser } from "./questions-browser";

export default function QuestionsPage() {
  return (
    <Suspense
      fallback={
        <>
          <PageHeader
            title="Questions"
            summary="Generate, validate and review Python assessment questions."
          />
          <TableSkeleton />
        </>
      }
    >
      <QuestionsBrowser />
    </Suspense>
  );
}
