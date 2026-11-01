"use client";

/**
 * Coverage grid for the live bank or a frozen set, plus the freeze form.
 * The scope lives in the URL (`?set=`); the freeze form shows only for the live bank.
 */

import { RefreshCw } from "lucide-react";
import { parseAsInteger, useQueryState } from "nuqs";
import { useMemo } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { EmptyState, QueryError, TableSkeleton } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useCoverage, useQuestionSets, useSyncTaxonomyClassroom } from "@/lib/api/queries";
import { pluralise } from "@/lib/display";
import { SECTIONS_BY_KEY } from "@/lib/navigation";
import { CoverageGrid } from "./components/coverage-grid";

const LIVE = "live";

export function CoverageScreen() {
  const section = SECTIONS_BY_KEY.coverage;
  const [setId, setSetId] = useQueryState("set", parseAsInteger);
  const scopedCoverage = useCoverage(setId ?? undefined);
  const questionSets = useQuestionSets();
  const syncLink = useSyncTaxonomyClassroom();

  const sets = useMemo(() => questionSets.data?.sets ?? [], [questionSets.data]);

  const report = scopedCoverage.data;

  /** Freeze this taxonomy's approved questions behind its own classroom link. */
  async function updateClassroomLink(curriculumVersionId: number) {
    try {
      const synced = await syncLink.mutateAsync(curriculumVersionId);
      toast.success(
        `Classroom link now serves snapshot #${synced.id} (${synced.question_count} questions).`,
      );
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not update the classroom link.");
    }
  }

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

      {sets.length > 0 ? (
        <Card>
          <CardContent className="flex flex-wrap items-center gap-3 py-4">
            <Select
              value={setId === null ? LIVE : String(setId)}
              onValueChange={(value) =>
                setSetId(value === LIVE ? null : Number.parseInt(value, 10))
              }
            >
              <SelectTrigger className="w-72" aria-label="Coverage scope">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={LIVE}>Live bank</SelectItem>
                {sets.map((set) => (
                  <SelectItem key={set.id} value={String(set.id)}>
                    #{set.id} · {set.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {report?.curriculum_version_id && setId === null ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={syncLink.isPending}
                onClick={() => void updateClassroomLink(report.curriculum_version_id as number)}
              >
                <RefreshCw className={syncLink.isPending ? "animate-spin" : undefined} />
                {syncLink.isPending ? "Updating..." : "Update classroom link"}
              </Button>
            ) : null}
            {setId !== null ? (
              <Button variant="ghost" size="sm" className="ml-auto" onClick={() => setSetId(null)}>
                Back to live bank
              </Button>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {scopedCoverage.isPending ? <TableSkeleton rows={6} /> : null}
      {scopedCoverage.isError ? <QueryError error={scopedCoverage.error} /> : null}

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
