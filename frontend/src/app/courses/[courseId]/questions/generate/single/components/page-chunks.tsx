"use client";

/**
 * The chunks on the PDF page currently in view, read from `/api/chunks?page=`.
 *
 * A page often holds the end of one chunk and the start of the next, so this lists every
 * chunk covering the page rather than guessing one. The selected chunk is the one Generate
 * uses; scrolling selects the first chunk that opens on the new page, and a click here
 * picks another. A book with no pages (DOCX) shows the selected chunk alone.
 */

import { QueryError } from "@/components/query-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useBookChunks, useChunk } from "@/lib/api/queries";
import { cn } from "@/lib/utils";

export function PageChunks({
  bookId,
  page,
  selectedChunkId,
  onSelect,
}: {
  bookId: number;
  page: number | null;
  selectedChunkId: string | null;
  onSelect: (chunkId: string) => void;
}) {
  const onPage = useBookChunks(page === null ? null : bookId, page);
  const selected = useChunk(page === null ? selectedChunkId : null);
  const chunks = page === null ? (selected.data ? [selected.data] : []) : (onPage.data?.chunks ?? []);
  const query = page === null ? selected : onPage;

  return (
    <div className="flex max-h-72 shrink-0 flex-col overflow-hidden rounded-[1rem] border">
      <div className="flex items-center justify-between border-b bg-muted/40 px-3 py-2.5">
        <span className="font-mono text-[0.67rem] text-muted-foreground uppercase tracking-[0.16em]">
          {page === null ? "Selected chunk" : `Chunks on page ${page}`}
        </span>
        <span className="font-mono text-[0.67rem] text-muted-foreground">{chunks.length}</span>
      </div>
      <div className="flex-1 space-y-2 overflow-y-auto p-2">
        {query.isError ? <QueryError error={query.error} /> : null}
        {query.isPending && (page !== null || selectedChunkId !== null) ? (
          <Skeleton className="h-20 w-full" />
        ) : null}
        {!query.isPending && chunks.length === 0 ? (
          <p className="p-2 text-muted-foreground text-sm">
            {page === null ? "Pick a chunk from the outline." : "No text was read from this page."}
          </p>
        ) : null}
        {chunks.map((chunk) => {
          const isSelected = chunk.id === selectedChunkId;
          return (
            <button
              key={chunk.id}
              type="button"
              aria-pressed={isSelected}
              onClick={() => onSelect(chunk.id)}
              className={cn(
                "block w-full rounded-lg border px-3 py-2 text-left transition-colors",
                isSelected ? "border-primary bg-primary/5" : "hover:bg-muted/50",
              )}
            >
              <span className="block font-mono text-[0.68rem] text-muted-foreground">
                {chunk.citation}
              </span>
              <span
                className={cn(
                  "mt-1 block whitespace-pre-wrap text-sm leading-6",
                  isSelected ? "" : "line-clamp-3",
                )}
              >
                {chunk.text}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
