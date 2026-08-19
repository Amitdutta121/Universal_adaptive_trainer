/**
 * How a book row is labelled on screen.
 *
 * Pure, and separate from the components so the wording that carries meaning — a
 * `partial` import is a caveat, not a failure — is decided in one place and can be
 * tested without rendering anything.
 *
 * Formatting every list shares — timestamps, counts, machine codes as prose — is
 * in `lib/display.ts` instead, because the curriculum screens need it too.
 */

import type { BookStatus, BookSummary, ExtractionWarning } from "@/lib/api/types";

export const BOOK_STATUS_LABEL: Record<BookStatus, string> = {
  imported: "imported",
  partial: "partial",
};

/** `partial` is not an error: the document validated, but it declares caveats. */
export const BOOK_STATUS_VARIANT: Record<BookStatus, "secondary" | "outline"> = {
  imported: "secondary",
  partial: "outline",
};

export const BOOK_STATUS_MEANING: Record<BookStatus, string> = {
  imported: "The document validated and declared no caveats.",
  partial: "The document validated but declares caveats, or a boundary was guessed.",
};

/** Warnings that describe a fault, as opposed to ones that merely state a fact. */
export function defects(warnings: readonly ExtractionWarning[]): ExtractionWarning[] {
  return warnings.filter((warning) => warning.severity === "defect");
}

/** A book's author line, or an em dash — never a guess. */
export function authorLabel(book: Pick<BookSummary, "author">): string {
  return book.author?.trim() || "—";
}

export function formatFileSize(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}
