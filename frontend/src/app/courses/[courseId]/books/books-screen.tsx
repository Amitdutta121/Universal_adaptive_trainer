"use client";

/**
 * Contents: the course's books and videos. Manage what is already imported, and
 * upload more through the "Upload content" modal in the header. Each row's type
 * (book or video) is read off how it was uploaded (`contentTypeOf`). The route and
 * API still call every source a book.
 *
 * Server state — the list, the guide, every mutation — belongs to TanStack Query
 * in `lib/api/queries.ts`. What this component owns is what the browser owns: the
 * search box, the type and status filters, and which row a dialog is open for.
 *
 * The filters live in the URL so a filtered view can be reloaded or shared.
 */

import { Upload } from "lucide-react";
import { parseAsString, parseAsStringLiteral, useQueryState } from "nuqs";
import { useMemo, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { EmptyState, QueryError, TableSkeleton } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useBooks } from "@/lib/api/queries";
import type { BookSummary } from "@/lib/api/types";
import { pluralise } from "@/lib/display";
import { SECTIONS_BY_KEY } from "@/lib/navigation";
import { CONTENT_TYPES, contentTypeOf } from "./book-display";
import { BookDeleteDialog } from "./components/book-delete-dialog";
import { BookEditDialog } from "./components/book-edit-dialog";
import { BookImportDialog } from "./components/book-import-dialog";
import { ContentDropZone } from "./components/content-drop-zone";
import { BooksTable } from "./components/books-table";

const TYPE_FILTERS = ["all", ...CONTENT_TYPES] as const;

const TYPE_FILTER_LABEL: Record<(typeof TYPE_FILTERS)[number], string> = {
  all: "All types",
  book: "Books",
  video: "Videos",
};

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
  const [type, setType] = useQueryState(
    "type",
    parseAsStringLiteral(TYPE_FILTERS).withDefault("all"),
  );
  const [search, setSearch] = useQueryState("q", parseAsString.withDefault(""));

  const [editing, setEditing] = useState<BookSummary | null>(null);
  const [deleting, setDeleting] = useState<BookSummary | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  // Set when a dropped YouTube link needs its transcript pasted in the uploader.
  const [transcriptLink, setTranscriptLink] = useState<string | undefined>();

  const books = useBooks();

  const visible = useMemo(() => {
    const all = books.data?.books ?? [];
    return all.filter(
      (book) =>
        (type === "all" || contentTypeOf(book) === type) &&
        (status === "all" || book.status === status) &&
        matches(book, search),
    );
  }, [books.data, type, status, search]);

  const section = SECTIONS_BY_KEY.books;
  const total = books.data?.total ?? 0;

  return (
    <>
      <PageHeader
        title={section.label}
        summary={section.summary}
        actions={
          <Button
            size="sm"
            onClick={() => {
              setTranscriptLink(undefined);
              setImportOpen(true);
            }}
          >
            <Upload />
            Upload content
          </Button>
        }
      />

      <Card>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value || null)}
              placeholder="Search title, author, producer or filename"
              className="max-w-xs"
              aria-label="Search contents"
            />
            <Select
              value={type}
              onValueChange={(value) =>
                setType(value === "all" ? null : (value as (typeof TYPE_FILTERS)[number]))
              }
            >
              <SelectTrigger className="w-36" aria-label="Filter by type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TYPE_FILTERS.map((value) => (
                  <SelectItem key={value} value={value}>
                    {TYPE_FILTER_LABEL[value]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
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
                ? pluralise(total, "item")
                : `${visible.length} of ${pluralise(total, "item")}`}
            </p>
          </div>

          {books.isPending ? <TableSkeleton /> : null}
          {books.isError ? <QueryError error={books.error} /> : null}

          {books.isSuccess && visible.length === 0 ? (
            total === 0 ? (
              <EmptyState
                title="Nothing has been uploaded yet"
                hint="Drop a PDF, Word or PowerPoint file or a YouTube link here, or use Upload content."
              />
            ) : (
              <EmptyState
                title="Nothing matches this filter"
                hint="Clear the search or choose a different status."
              />
            )
          ) : null}

          {visible.length > 0 ? (
            <BooksTable books={visible} onEdit={setEditing} onDelete={setDeleting} />
          ) : null}
        </CardContent>
      </Card>

      <ContentDropZone
        disabled={importOpen}
        onNeedsTranscript={(url) => {
          setTranscriptLink(url);
          setImportOpen(true);
        }}
      />
      {/* Keyed so a link handed over by a page drop starts a fresh uploader. */}
      <BookImportDialog
        key={transcriptLink ?? "uploader"}
        open={importOpen}
        onOpenChange={setImportOpen}
        initialLink={transcriptLink}
      />
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
