/**
 * The coverage route shell.
 *
 * `CoverageScreen` keeps which snapshot the grid is pointed at in the URL
 * (`?set=`), which means it reads search params, which Next requires to sit
 * inside a Suspense boundary — without one the whole route opts out of static
 * rendering at build time.
 */

import { Suspense } from "react";
import { PageHeader } from "@/components/page-header";
import { TableSkeleton } from "@/components/query-state";
import { SECTIONS_BY_KEY } from "@/lib/navigation";
import { CoverageScreen } from "./coverage-screen";

export default function CoveragePage() {
  const section = SECTIONS_BY_KEY.coverage;
  return (
    <Suspense
      fallback={
        <>
          <PageHeader title={section.label} summary={section.summary} />
          <TableSkeleton />
        </>
      }
    >
      <CoverageScreen />
    </Suspense>
  );
}
