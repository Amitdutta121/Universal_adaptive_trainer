"use client";

/**
 * The chunk being read, under the sheet.
 *
 * Section text is stored verbatim and may open with an indented code listing, so
 * it is rendered in a pre-wrapped block: collapsing that whitespace would destroy
 * the listing. Nothing here is editable — this is the evidence for the decision
 * being made one row above.
 */

import { BookOpen, X } from "lucide-react";
import { QueryError } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useSection } from "@/lib/api/queries";
import type { SheetRow } from "../spec-sheet-types";

export function ChunkPreview({ row, onClose }: { row: SheetRow | null; onClose: () => void }) {
  const { data, isPending, isError, error } = useSection(
    row?.bookId ?? null,
    row?.sectionId ?? null,
  );

  if (!row) {
    return (
      <div className="flex items-center gap-2 border-border/70 border-t bg-muted/20 px-5 py-4 text-muted-foreground text-sm">
        <BookOpen className="size-4" />
        Select a chunk name to read its text before deciding what it can carry.
      </div>
    );
  }

  return (
    <section className="border-border/70 border-t bg-background/80">
      <header className="flex flex-wrap items-center gap-2 border-border/70 border-b px-5 py-3">
        <h3 className="font-heading text-base tracking-[-0.02em]">{row.title}</h3>
        {row.existingQuestionCount > 0 ? (
          <Badge variant="secondary" className="font-mono text-[0.65rem]">
            {row.existingQuestionCount} already made
          </Badge>
        ) : (
          <Badge variant="outline" className="text-[0.65rem]">
            no questions yet
          </Badge>
        )}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="ml-auto h-7 px-2 text-muted-foreground"
          onClick={onClose}
        >
          <X className="size-3.5" /> Close
        </Button>
      </header>

      <div className="space-y-3 px-5 py-4">
        {isError ? <QueryError error={error} /> : null}
        {isPending ? <Skeleton className="h-28 w-full" /> : null}
        {data ? (
          <>
            <p className="font-mono text-[0.7rem] text-muted-foreground">{data.citation}</p>
            <pre className="max-h-64 max-w-[76ch] overflow-auto whitespace-pre-wrap font-sans text-[0.85rem] text-foreground leading-6">
              {data.text}
            </pre>
          </>
        ) : null}
      </div>
    </section>
  );
}
