/**
 * The coverage route shell.
 *
 * The Suspense fallback shows the header and a skeleton while the screen loads.
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
