"use client";

/**
 * Rename one topic or subtopic.
 *
 * Shared by the version tree and the subtopic page, because it is one edit with
 * one meaning wherever it is offered.
 *
 * Only the changed fields are sent: an empty description is a real correction and
 * clears the field, while an untouched one must not be resent as a change. The
 * description this dialog explains is the promise the professor most needs to
 * trust — the stable id does not move, so weakness measured on this skill stays
 * attached to it.
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
import { Textarea } from "@/components/ui/textarea";
import { useRenameCurriculumItem } from "@/lib/api/queries";
import type { Schemas } from "@/lib/api/types";

/** `TaxonomyTopic`/`TaxonomySubtopic` declare these bounds. */
const NAME_MAX_LENGTH = 300;
const DESCRIPTION_MAX_LENGTH = 2000;

export interface RenameTarget {
  kind: "topic" | "subtopic";
  id: number;
  name: string;
  description: string | null;
}

export function ItemRenameDialog({
  target,
  open,
  onOpenChange,
}: {
  target: RenameTarget | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const rename = useRenameCurriculumItem();
  const nameFieldId = useId();
  const descriptionFieldId = useId();
  // Safe to seed from props: the parent keys this component on the chosen row.
  const [name, setName] = useState(target?.name ?? "");
  const [description, setDescription] = useState(target?.description ?? "");

  if (!target) return null;

  const changed: Schemas["CurriculumItemLabelUpdate"] = {
    ...(name !== target.name ? { name } : {}),
    ...(description !== (target.description ?? "") ? { description } : {}),
  };
  const hasChanges = Object.keys(changed).length > 0;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!target) return;
    try {
      const updated = await rename.mutateAsync({
        kind: target.kind,
        itemId: target.id,
        body: changed,
      });
      toast.success(`Saved “${updated.name}”`, {
        description: "Its stable id is unchanged, so any measured weakness stays attached to it.",
      });
      onOpenChange(false);
    } catch {
      // Rendered from `rename.error` below, with the backend's own wording — a
      // duplicate sibling name is refused there, and it names the sibling.
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Rename this {target.kind}</DialogTitle>
            <DialogDescription>
              The display name only. The stable id stays as it is, so questions tagged against this{" "}
              {target.kind} and any weakness measured on it stay attached.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            <Label htmlFor={nameFieldId}>Name</Label>
            <Input
              id={nameFieldId}
              value={name}
              maxLength={NAME_MAX_LENGTH}
              onChange={(event) => setName(event.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor={descriptionFieldId}>
              Description <span className="text-muted-foreground">(optional)</span>
            </Label>
            <Textarea
              id={descriptionFieldId}
              value={description}
              maxLength={DESCRIPTION_MAX_LENGTH}
              className="h-24"
              onChange={(event) => setDescription(event.target.value)}
            />
          </div>

          {rename.error ? <QueryError error={rename.error} /> : null}

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!hasChanges || rename.isPending}>
              {rename.isPending ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
