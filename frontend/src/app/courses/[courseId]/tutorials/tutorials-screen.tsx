"use client";

/**
 * The tutorials route: the taxonomy's tutorial recipes (`recipe-approval.tsx`), each with a
 * sample of its blocks as students see them. New recipes are made from the header's
 * "Create a recipe" (`create-recipe-button.tsx`); with live tutorials on, blocks are written as
 * students need them, so nothing is generated from this page.
 */

import { EmptyState, TableSkeleton } from "@/components/query-state";
import { useApprovedCurriculum } from "@/lib/api/queries";
import { RecipeApproval } from "./recipe-approval";

export function TutorialsScreen() {
  const approved = useApprovedCurriculum();

  if (approved.isPending) return <TableSkeleton rows={3} />;
  if (approved.isError) {
    return (
      <EmptyState
        title="No approved taxonomy yet"
        hint="Tutorial blocks are written per subtopic. Approve a taxonomy under Curriculum first."
      />
    );
  }
  return <RecipeApproval versionId={approved.data.version.id} />;
}
