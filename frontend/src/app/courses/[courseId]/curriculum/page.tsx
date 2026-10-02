/**
 * The curriculum route shell.
 *
 * `CurriculumScreen` keeps its search and status filter in the URL, which means it
 * reads search params, which Next requires to sit inside a Suspense boundary —
 * without one the whole route opts out of static rendering at build time.
 */

import { Suspense } from "react";
import { PageHeader } from "@/components/page-header";
import { TableSkeleton } from "@/components/query-state";
import { SECTIONS_BY_KEY } from "@/lib/navigation";
import { CurriculumScreen } from "./curriculum-screen";

export default function CurriculumPage() {
  const section = SECTIONS_BY_KEY.curriculum;
  return (
    <Suspense
      fallback={
        <>
          <PageHeader title={section.label} summary={section.summary} />
          <TableSkeleton />
        </>
      }
    >
      <CurriculumScreen />
    </Suspense>
  );
}
