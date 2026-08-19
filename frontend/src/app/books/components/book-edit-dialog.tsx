"use client";

/**
 * Edit a book's labels — title, author, notes.
 *
 * Only the labels. Chapters, sections and section text are declared by the
 * imported document (ADR-015), so a wrong boundary is corrected by fixing the
 * document and importing it again, and this form says so rather than leaving a
 * professor hunting for a field that does not exist.
 *
 * A cleared author or note is sent as an empty string, which the API reads as
 * "clear it"; an untouched field is not sent at all.
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
import { useUpdateBook } from "@/lib/api/queries";
import type { BookSummary, Schemas } from "@/lib/api/types";

export function BookEditDialog({
  book,
  open,
  onOpenChange,
}: {
  book: BookSummary | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const updateBook = useUpdateBook();
  const titleId = useId();
  const authorId = useId();
  const notesId = useId();

  // Keyed on the book below, so opening a different row remounts with its values.
  const [title, setTitle] = useState(book?.title ?? "");
  const [author, setAuthor] = useState(book?.author ?? "");
  const [notes, setNotes] = useState(book?.notes ?? "");

  if (!book) return null;

  const changed: Schemas["BookMetadataUpdate"] = {
    ...(title !== book.title ? { title } : {}),
    ...(author !== (book.author ?? "") ? { author } : {}),
    ...(notes !== (book.notes ?? "") ? { notes } : {}),
  };
  const hasChanges = Object.keys(changed).length > 0;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!book || !hasChanges) return;
    try {
      const updated = await updateBook.mutateAsync({ bookId: book.id, body: changed });
      toast.success(`Saved “${updated.title}”`);
      onOpenChange(false);
    } catch {
      // Shown below with the backend's own message — a blank title is refused there.
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Edit book</DialogTitle>
            <DialogDescription>
              Labels only. Chapters and section text come from the imported document — to correct
              those, fix the document and import it again.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            <Label htmlFor={titleId}>Title</Label>
            <Input
              id={titleId}
              value={title}
              maxLength={500}
              onChange={(event) => setTitle(event.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor={authorId}>
              Author <span className="text-muted-foreground">(empty if none is printed)</span>
            </Label>
            <Input
              id={authorId}
              value={author}
              maxLength={500}
              onChange={(event) => setAuthor(event.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor={notesId}>
              Notes <span className="text-muted-foreground">(optional)</span>
            </Label>
            <Textarea
              id={notesId}
              value={notes}
              maxLength={5000}
              className="h-[6rem]"
              onChange={(event) => setNotes(event.target.value)}
              placeholder="Why this book is here, which course it serves…"
            />
          </div>

          {updateBook.error ? <QueryError error={updateBook.error} /> : null}

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!hasChanges || updateBook.isPending}>
              {updateBook.isPending ? "Saving…" : "Save changes"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
