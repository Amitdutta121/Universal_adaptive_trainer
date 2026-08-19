"use client";

/**
 * Rename a curriculum version.
 *
 * The label is the only field. A version's topics and subtopics come from the
 * document it was uploaded from, and its status is decided by uploading a
 * replacement — neither is editable here, and neither is even expressible: the
 * request model has one field.
 */

import { useId, useState } from "react";
import { toast } from "sonner";
import { QueryError } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useUpdateCurriculumVersion } from "@/lib/api/queries";
import type { CurriculumVersionSummary } from "@/lib/api/types";

/** `TaxonomyDocument.label` declares `max_length=200`. */
const LABEL_MAX_LENGTH = 200;

export function VersionEditDialog({
  version,
  open,
  onOpenChange,
}: {
  version: CurriculumVersionSummary | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const updateVersion = useUpdateCurriculumVersion();
  const labelFieldId = useId();
  // Safe to seed from props: the parent keys this component on the chosen row.
  const [label, setLabel] = useState(version?.label ?? "");

  if (!version) return null;

  const trimmed = label.trim();
  const canSave = trimmed.length > 0 && trimmed !== version.label;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!version) return;
    try {
      const updated = await updateVersion.mutateAsync({
        versionId: version.id,
        body: { label: trimmed },
      });
      toast.success(`Renamed to “${updated.version.label}”`);
      onOpenChange(false);
    } catch {
      // Rendered from `updateVersion.error` below, with the backend's own wording.
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Rename this curriculum version</DialogTitle>
            <DialogDescription>
              The label only. Its topics and subtopics come from the uploaded document — to change
              the structure, fix the document and upload it again.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            <Label htmlFor={labelFieldId}>Label</Label>
            <Input
              id={labelFieldId}
              value={label}
              maxLength={LABEL_MAX_LENGTH}
              onChange={(event) => setLabel(event.target.value)}
            />
          </div>

          {updateVersion.error ? <QueryError error={updateVersion.error} /> : null}

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!canSave || updateVersion.isPending}>
              {updateVersion.isPending ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
