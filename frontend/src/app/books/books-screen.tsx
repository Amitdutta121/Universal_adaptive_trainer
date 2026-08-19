"use client";

/**
 * The books library: import a document, and manage what is already imported.
 *
 * Server state — the list, the guide, every mutation — belongs to TanStack Query
 * in `lib/api/queries.ts`. What this component owns is what the browser owns: the
 * search box, the status filter, and which row a dialog is open for.
 *
 * The filter lives in the URL so a filtered view can be reloaded or shared.
 */

import { parseAsString, parseAsStringLiteral, useQueryState } from "nuqs";
import { useMemo, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { EmptyState, QueryError, TableSkeleton } from "@/components/query-state";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useBookDocumentGuide, useBooks } from "@/lib/api/queries";
import type { BookSummary } from "@/lib/api/types";
import { SECTIONS_BY_KEY } from "@/lib/navigation";
import { pluralise } from "@/lib/display";
import { BookDeleteDialog } from "./components/book-delete-dialog";
import { BookEditDialog } from "./components/book-edit-dialog";
import { BookUploadCard } from "./components/book-upload-card";
import { BooksTable } from "./components/books-table";
import { DocumentGuideCard } from "./components/document-guide-card";

const STATUS_FILTERS = ["all", "imported", "partial"] as const;

const STATUS_FILTER_LABEL: Record<(typeof STATUS_FILTERS)[number], string> = {
  all: "All statuses",
  imported: "Imported",
  partial: "Partial",
};

function matches(book: BookSummary, search: string): boolean {
  const needle = search.trim().toLowerCase();
  if (!needle) return true;
  return [book.title, book.author, book.producer, book.original_filename]
    .filter((value): value is string => Boolean(value))
    .some((value) => value.toLowerCase().includes(needle));
}

export function BooksScreen() {
  const [status, setStatus] = useQueryState(
    "status",
    parseAsStringLiteral(STATUS_FILTERS).withDefault("all"),
  );
  const [search, setSearch] = useQueryState("q", parseAsString.withDefault(""));

  const [editing, setEditing] = useState<BookSummary | null>(null);
  const [deleting, setDeleting] = useState<BookSummary | null>(null);

  const books = useBooks();
  const guide = useBookDocumentGuide();

  const visible = useMemo(() => {
    const all = books.data?.books ?? [];
    return all.filter(
      (book) => (status === "all" || book.status === status) && matches(book, search),
    );
  }, [books.data, status, search]);

  const section = SECTIONS_BY_KEY.books;
  const total = books.data?.total ?? 0;

  return (
    <>
      <PageHeader title={section.label} summary={section.summary} />

      <BookUploadCard guide={guide.data} />

      <DocumentGuideCard guide={guide.data} isPending={guide.isPending} error={guide.error} />

      <Card>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value || null)}
              placeholder="Search title, author, producer or filename"
              className="max-w-xs"
              aria-label="Search books"
            />
            <Select
              value={status}
              onValueChange={(value) =>
                setStatus(value === "all" ? null : (value as (typeof STATUS_FILTERS)[number]))
              }
            >
              <SelectTrigger className="w-44" aria-label="Filter by status">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {STATUS_FILTERS.map((value) => (
                  <SelectItem key={value} value={value}>
                    {STATUS_FILTER_LABEL[value]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="ml-auto text-muted-foreground text-sm">
              {visible.length === total
                ? pluralise(total, "book")
                : `${visible.length} of ${pluralise(total, "book")}`}
            </p>
          </div>

          {books.isPending ? <TableSkeleton /> : null}
          {books.isError ? <QueryError error={books.error} /> : null}

          {books.isSuccess && visible.length === 0 ? (
            total === 0 ? (
              <EmptyState
                title="No books have been imported yet"
                hint="Copy the prompt above, have an assistant turn your textbook into a document, then import it."
              />
            ) : (
              <EmptyState
                title="No book matches this filter"
                hint="Clear the search or choose a different status."
              />
            )
          ) : null}

          {visible.length > 0 ? (
            <BooksTable books={visible} onEdit={setEditing} onDelete={setDeleting} />
          ) : null}
        </CardContent>
      </Card>

      {/* Keyed so the form remounts with the values of whichever row was chosen. */}
      <BookEditDialog
        key={`edit-${editing?.id ?? "none"}`}
        book={editing}
        open={editing !== null}
        onOpenChange={(open) => !open && setEditing(null)}
      />
      <BookDeleteDialog
        key={`delete-${deleting?.id ?? "none"}`}
        book={deleting}
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
      />
    </>
  );
}
