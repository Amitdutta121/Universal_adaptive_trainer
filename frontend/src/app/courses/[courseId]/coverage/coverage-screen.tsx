"use client";

/** Coverage grid for the live bank: one square per subtopic of the approved taxonomy. */

import { PageHeader } from "@/components/page-header";
import { EmptyState, QueryError, TableSkeleton } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import { useCoverage } from "@/lib/api/queries";
import { pluralise } from "@/lib/display";
import { SECTIONS_BY_KEY } from "@/lib/navigation";
import { CoverageGrid } from "./components/coverage-grid";

export function CoverageScreen() {
  const section = SECTIONS_BY_KEY.coverage;
  const coverage = useCoverage();
  const report = coverage.data;

  return (
    <>
      <PageHeader
        title={section.label}
        summary="Compact topic map. Hover a square for subtopic details."
        actions={
          report ? (
            <Badge variant="outline" className="h-7 rounded-full px-3 font-mono tracking-[0.08em]">
              {pluralise(report.question_count, "question")}
            </Badge>
          ) : null
        }
      />

      {coverage.isPending ? <TableSkeleton rows={6} /> : null}
      {coverage.isError ? <QueryError error={coverage.error} /> : null}

      {report ? (
        report.curriculum_version_id === null ? (
          <EmptyState title="No taxonomy yet" hint="Create one on the Curriculum page." />
        ) : report.total_cells === 0 ? (
          <EmptyState title="This taxonomy has no subtopics" />
        ) : (
          <CoverageGrid report={report} />
        )
      ) : null}
    </>
  );
}
