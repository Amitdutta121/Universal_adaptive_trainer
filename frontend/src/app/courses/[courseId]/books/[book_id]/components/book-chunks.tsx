"use client";

/**
 * The book's current chunks, in reading order, grouped by the page each one starts on.
 *
 * A chunk is what questions are generated from and what they cite. "Go to page" narrows the
 * list to the chunks covering one page (`/api/chunks?page=`), the same lookup the
 * generate screen makes as the PDF scrolls.
 */

import { useMemo, useState } from "react";
import { CourseLink } from "@/components/course-link";
import { QueryError, TableSkeleton } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useBookChunks } from "@/lib/api/queries";
import type { Schemas } from "@/lib/api/types";

type Chunk = Schemas["ChunkOut"];

const HEADING_SEPARATOR = " › ";

function ChunkRow({ bookId, chunk }: { bookId: number; chunk: Chunk }) {
  return (
    <li className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-t py-2 text-sm first:border-t-0">
      <CourseLink
        href={`/books/${bookId}/chunks/${chunk.id}`}
        className="min-w-0 flex-1 font-medium hover:underline"
      >
        {chunk.heading_path.length > 0 ? chunk.heading_path.join(HEADING_SEPARATOR) : "No heading"}
      </CourseLink>
      <span className="text-muted-foreground text-xs tabular-nums">
        {chunk.text.length.toLocaleString()} chars
      </span>
      <p className="w-full truncate text-muted-foreground text-xs">{chunk.text}</p>
    </li>
  );
}

export function BookChunks({ bookId, pageCount }: { bookId: number; pageCount: number | null }) {
  const [pageInput, setPageInput] = useState("");
  const [page, setPage] = useState<number | null>(null);
  const { data, isPending, isError, error } = useBookChunks(bookId, page);

  const byPage = useMemo(() => {
    const groups = new Map<string, Chunk[]>();
    for (const chunk of data?.chunks ?? []) {
      const key = chunk.page_start === null ? "No page" : `Page ${chunk.page_start}`;
      groups.set(key, [...(groups.get(key) ?? []), chunk]);
    }
    return [...groups.entries()];
  }, [data]);

  const goToPage = () => {
    const value = Number(pageInput);
    setPage(Number.isInteger(value) && value >= 1 ? value : null);
  };

  return (
    <div className="space-y-4">
      <form
        className="flex flex-wrap items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          goToPage();
        }}
      >
        <Input
          type="number"
          min={1}
          max={pageCount ?? undefined}
          inputMode="numeric"
          placeholder="Page"
          aria-label="Go to page"
          className="h-8 w-24"
          value={pageInput}
          onChange={(event) => setPageInput(event.target.value)}
        />
        <Button type="submit" variant="outline" size="sm">
          Go to page
        </Button>
        {page !== null ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => {
              setPage(null);
              setPageInput("");
            }}
          >
            Show all
          </Button>
        ) : null}
        {data ? (
          <Badge variant="secondary" className="ml-auto font-mono text-[0.65rem]">
            {page === null ? `${data.total} chunks` : `${data.total} on page ${page}`}
          </Badge>
        ) : null}
      </form>

      {isError ? <QueryError error={error} /> : null}
      {isPending ? <TableSkeleton /> : null}
      {data && data.total === 0 ? (
        <p className="text-muted-foreground text-sm">
          {page === null
            ? "This book has no chunks. It was imported before chunking; re-import its file."
            : "No text was read from this page."}
        </p>
      ) : null}

      <div className="space-y-3">
        {byPage.map(([label, chunks]) => (
          <section key={label}>
            <h3 className="font-mono text-[0.68rem] text-muted-foreground uppercase tracking-[0.16em]">
              {label}
            </h3>
            <ul>
              {chunks.map((chunk) => (
                <ChunkRow key={chunk.id} bookId={bookId} chunk={chunk} />
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
