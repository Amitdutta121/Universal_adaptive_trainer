"use client";

/**
 * Delete a book, its structure and its retained document.
 *
 * The backend refuses while questions cite the book: their grounding lives in a
 * frozen spec rather than a foreign key, so deleting the sections does not delete
 * the questions — it leaves their citation pointing at nothing (ADR-036).
 *
 * That refusal is shown here as what it is, with the count the API named, and an
 * explicit second button to overrule it. The console does not pre-empt the check
 * or decide on the professor's behalf; it repeats the request with `force` only
 * after they have read the cost.
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
import { useDeleteBook } from "@/lib/api/queries";
import type { BookSummary } from "@/lib/api/types";
import { pluralise } from "@/lib/display";

export function BookDeleteDialog({
  book,
  open,
  onOpenChange,
  onDeleted,
}: {
  book: BookSummary | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called after a successful delete — the detail page uses it to navigate away. */
  onDeleted?: () => void;
}) {
  const deleteBook = useDeleteBook();
  const [conflict, setConflict] = useState<ApiError | null>(null);

  useEffect(() => {
    if (!open) {
      setConflict(null);
      deleteBook.reset();
    }
  }, [open, deleteBook.reset]);

  if (!book) return null;

  async function remove(force: boolean) {
    if (!book) return;
    try {
      const result = await deleteBook.mutateAsync({ bookId: book.id, force });
      const stranded = result.stranded_question_count;
      toast.success(`Deleted “${book.title}”`, {
        description: stranded
          ? `${pluralise(stranded, "question")} now cite sections that no longer exist.`
          : "Its structure and retained document were removed.",
      });
      onOpenChange(false);
      onDeleted?.();
    } catch (error) {
      // 409 is the backend refusing until the cost is acknowledged, not a failure.
      if (error instanceof ApiError && error.status === 409) setConflict(error);
      else {
        toast.error("Could not delete this book", {
          description: error instanceof Error ? error.message : undefined,
        });
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Delete “{book.title}”?</DialogTitle>
          <DialogDescription>
            This removes the book, its chapters and sections, and the document it was imported from.
            It cannot be undone — but the document can be imported again.
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
            Cancel
          </Button>
          {conflict ? (
            <Button
              variant="destructive"
              disabled={deleteBook.isPending}
              onClick={() => remove(true)}
            >
              <Trash2 />
              Delete anyway
            </Button>
          ) : (
            <Button
              variant="destructive"
              disabled={deleteBook.isPending}
              onClick={() => remove(false)}
            >
              <Trash2 />
              {deleteBook.isPending ? "Deleting…" : "Delete book"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
