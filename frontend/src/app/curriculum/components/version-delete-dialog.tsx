"use client";

/**
 * Delete a curriculum version, its topics and its subtopics.
 *
 * Unlike a book, some refusals here have no override. A frozen question set that
 * names this version can never be edited or deleted, and the approved version is
 * what generation is grounded in — so the backend answers those with
 * `conflict_not_overridable` rather than the plain `resource_in_use`.
 *
 * That code is the whole reason this dialog is not a copy of the book one: it
 * decides whether to offer "Delete anyway" from what the API said, not by
 * re-deriving the rule in the browser. Offering an override that is guaranteed to
 * fail would be worse than not offering one.
 */

import { AlertTriangle, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ApiError } from "@/lib/api/client";
import { useDeleteCurriculumVersion } from "@/lib/api/queries";
import type { CurriculumVersionSummary } from "@/lib/api/types";
import { pluralise } from "@/lib/display";

/** The code the backend uses for a refusal `force` cannot clear. */
const NOT_OVERRIDABLE = "conflict_not_overridable";

export function VersionDeleteDialog({
  version,
  open,
  onOpenChange,
  onDeleted,
}: {
  version: CurriculumVersionSummary | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called after a successful delete — the detail page uses it to navigate away. */
  onDeleted?: () => void;
}) {
  const deleteVersion = useDeleteCurriculumVersion();
  const [conflict, setConflict] = useState<ApiError | null>(null);

  useEffect(() => {
    if (!open) {
      setConflict(null);
      deleteVersion.reset();
    }
  }, [open, deleteVersion.reset]);

  if (!version) return null;

  const overridable = conflict !== null && conflict.code !== NOT_OVERRIDABLE;

  async function remove(force: boolean) {
    if (!version) return;
    try {
      const result = await deleteVersion.mutateAsync({ versionId: version.id, force });
      const { question_count, student_count } = result.stranded;
      const stranded = [
        question_count ? pluralise(question_count, "question") : null,
        student_count ? pluralise(student_count, "student") : null,
      ].filter(Boolean);
      toast.success(`Deleted “${version.label}”`, {
        description: stranded.length
          ? `${stranded.join(" and ")} now name topics that no longer exist.`
          : `${pluralise(result.deleted_topic_count, "topic")} and ${pluralise(
              result.deleted_subtopic_count,
              "subtopic",
            )} were removed.`,
      });
      onOpenChange(false);
      onDeleted?.();
    } catch (error) {
      // 409 is the backend refusing, not a failure. Whether an override exists
      // is the code's answer to give, not this component's.
      if (error instanceof ApiError && error.status === 409) setConflict(error);
      else {
        toast.error("Could not delete this version", {
          description: error instanceof Error ? error.message : undefined,
        });
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Delete “{version.label}”?</DialogTitle>
          <DialogDescription>
            This removes the version and every topic and subtopic in it. It cannot be undone, and
            the document is not retained — upload your own copy again to recreate it.
          </DialogDescription>
        </DialogHeader>

        {conflict ? (
          <Alert variant="destructive">
            <AlertTriangle />
            <AlertTitle>{conflict.message}</AlertTitle>
            <AlertDescription>
              <p>{conflict.detail}</p>
            </AlertDescription>
          </Alert>
        ) : null}

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {conflict && !overridable ? "Close" : "Cancel"}
          </Button>
          {conflict ? (
            // Only where the backend said an override exists. A refusal it cannot
            // clear gets no button at all.
            overridable ? (
              <Button
                variant="destructive"
                disabled={deleteVersion.isPending}
                onClick={() => remove(true)}
              >
                <Trash2 />
                Delete anyway
              </Button>
            ) : null
          ) : (
            <Button
              variant="destructive"
              disabled={deleteVersion.isPending}
              onClick={() => remove(false)}
            >
              <Trash2 />
              {deleteVersion.isPending ? "Deleting…" : "Delete version"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
