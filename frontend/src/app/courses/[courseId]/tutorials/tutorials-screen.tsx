"use client";

/**
 * The tutorials route: the taxonomy's tutorial styles (`recipe-approval.tsx`), each opened in a
 * modal with examples and a gallery of its tutorials (`style-dialog.tsx`). New styles are made
 * from the header's "Create a style" (`create-recipe-button.tsx`); with live tutorials on,
 * blocks are written as students need them, so nothing is generated from this page.
 */

import { useMemo } from "react";
import { EmptyState, TableSkeleton } from "@/components/query-state";
import { useApprovedCurriculum } from "@/lib/api/queries";
import { RecipeApproval } from "./recipe-approval";

export function TutorialsScreen() {
  const approved = useApprovedCurriculum();
  const subtopicNames = useMemo(
    () =>
      new Map(
        (approved.data?.topics ?? []).flatMap((topic) =>
          topic.subtopics.map((subtopic) => [subtopic.id, subtopic.name] as const),
        ),
      ),
    [approved.data],
  );

  if (approved.isPending) return <TableSkeleton rows={3} />;
  if (approved.isError) {
    return (
      <EmptyState
        title="No approved taxonomy yet"
        hint="Tutorials are written per subtopic. Approve a taxonomy under Curriculum first."
      />
    );
  }
  return <RecipeApproval versionId={approved.data.version.id} subtopicNames={subtopicNames} />;
}
