"use client";

/**
 * The course's uploaded files, at the top right of the chat: what the assistant can read, with
 * Add and Remove, so the professor can see and change the material without leaving the chat.
 *
 * The list opens under the header like "Past chats" does, not in a portal: the side panel sits
 * above the Studio's portalled popovers. Adding imports a file exactly like dropping it in the
 * chat (`useImportBook`, checked by `uploadProblem`); it shows in the list once its import job
 * finishes. Removing asks once more in place, then deletes the file; a file questions still cite
 * is refused with the backend's own message.
 */

import { FileText, Loader2, Paperclip, Plus, Trash2, X } from "lucide-react";
import { type ChangeEvent, useRef, useState } from "react";
import { toast } from "sonner";
import { uploadProblem } from "@/app/courses/[courseId]/books/components/book-import-dialog";
import { useBooks, useConfig, useDeleteBook, useImportBook } from "@/lib/api/queries";
import { cn } from "@/lib/utils";

const iconButton =
  "inline-flex size-8 items-center justify-center rounded-full text-muted-foreground transition hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong.";
}

/** The files list and its Add and Remove actions, without the trigger (tested on its own). */
export function MaterialsPanel({ onClose }: { onClose: () => void }) {
  const books = useBooks();
  const config = useConfig();
  const importBook = useImportBook();
  const deleteBook = useDeleteBook();
  const input = useRef<HTMLInputElement>(null);
  const [confirming, setConfirming] = useState<number | null>(null);
  const extensions = config.data?.supported_book_extensions ?? [".pdf"];

  const add = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    for (const file of files) {
      const problem = uploadProblem(file, extensions, config.data?.max_book_upload_mb);
      if (problem) {
        toast.error(file.name, { description: problem });
        continue;
      }
      try {
        await importBook.mutateAsync({ file });
        toast.info(`Importing ${file.name}`, {
          description: "It shows here, and the assistant can read it, once the import finishes.",
        });
      } catch (error) {
        toast.error(file.name, { description: errorText(error) });
      }
    }
  };

  const remove = async (bookId: number, title: string) => {
    setConfirming(null);
    try {
      await deleteBook.mutateAsync({ bookId });
      toast.success(`Removed ${title}`);
    } catch (error) {
      toast.error(`${title} was not removed`, { description: errorText(error) });
    }
  };

  const list = books.data?.books ?? [];
  return (
    <div className="absolute inset-x-0 top-full z-10 max-h-96 overflow-y-auto border-b bg-background shadow-sm">
      <div className="flex items-center justify-between px-4 pt-3 pb-1">
        <p className="font-medium text-sm">Course files</p>
        <button
          type="button"
          className={cn(iconButton, "size-7")}
          aria-label="Close"
          onClick={onClose}
        >
          <X className="size-3.5" />
        </button>
      </div>
      {books.isLoading ? (
        <p className="px-4 py-2 text-muted-foreground text-sm">Loading…</p>
      ) : list.length === 0 ? (
        <p className="px-4 py-2 text-muted-foreground text-sm">
          No files yet. Add a syllabus, book or slides for the assistant to read.
        </p>
      ) : (
        <ul className="py-1">
          {list.map((book) => (
            <li key={book.id} className="flex items-center gap-2 px-4 py-1.5 text-sm">
              <FileText className="size-4 shrink-0 text-muted-foreground" />
              <span className="min-w-0 flex-1 truncate" title={book.original_filename}>
                {book.title}
              </span>
              {confirming === book.id ? (
                <span className="flex shrink-0 items-center gap-1 text-xs">
                  <button
                    type="button"
                    className="rounded-md px-1.5 py-0.5 font-medium text-destructive hover:bg-destructive/10"
                    onClick={() => remove(book.id, book.title)}
                  >
                    Remove
                  </button>
                  <button
                    type="button"
                    className="rounded-md px-1.5 py-0.5 text-muted-foreground hover:bg-muted"
                    onClick={() => setConfirming(null)}
                  >
                    Keep
                  </button>
                </span>
              ) : (
                <button
                  type="button"
                  className={cn(iconButton, "size-7 shrink-0")}
                  aria-label={`Remove ${book.title}`}
                  title="Remove file"
                  disabled={deleteBook.isPending}
                  onClick={() => setConfirming(book.id)}
                >
                  <Trash2 className="size-3.5" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      <div className="border-t px-4 py-2">
        <input
          ref={input}
          type="file"
          multiple
          accept={extensions.join(",")}
          className="hidden"
          aria-label="Add files"
          onChange={add}
        />
        <button
          type="button"
          className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-sm hover:bg-muted"
          disabled={importBook.isPending}
          onClick={() => input.current?.click()}
        >
          {importBook.isPending ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Plus className="size-4" />
          )}
          Add files
        </button>
      </div>
    </div>
  );
}

/** The trigger, with how many files the course has; renders the panel under its header. */
export function ChatMaterialsButton({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const books = useBooks();
  const count = books.data?.books.length ?? 0;
  return (
    <button
      type="button"
      className={cn(iconButton, "relative", open && "bg-muted text-foreground")}
      aria-label={`Course files (${count})`}
      aria-expanded={open}
      title="Course files"
      onClick={onToggle}
    >
      <Paperclip className="size-4" />
      {count ? (
        <span className="absolute -top-0.5 -right-0.5 min-w-4 rounded-full bg-primary px-1 text-center font-medium text-[10px] text-primary-foreground leading-4">
          {count}
        </span>
      ) : null}
    </button>
  );
}
