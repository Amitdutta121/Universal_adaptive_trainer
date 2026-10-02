"use client";

/**
 * Filters, the sheet default, and the bulk fills.
 *
 * The bulk fills are what make per-chunk control usable: without them a professor
 * fills forty rows one stepper at a time. They write only to selected rows, so
 * what a fill touched is visible on the sheet immediately after it runs.
 */

import { Eraser, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { QuestionType } from "@/lib/api/types";
import type { BookSummary } from "../spec-sheet-types";
import type { FillPattern } from "../use-chunk-specs";
import type { SheetChapter, SheetFilters } from "../use-sheet-rows";
import { FormatPicker } from "./format-picker";

const FILLS: ReadonlyArray<{ label: string; pattern: FillPattern }> = [
  { label: "1 of each", pattern: { easy: 1, medium: 1, hard: 1 } },
  { label: "3 medium", pattern: { easy: 0, medium: 3, hard: 0 } },
  { label: "Clear rows", pattern: { easy: 0, medium: 0, hard: 0 } },
];

function FieldLabel({ children }: { children: string }) {
  return (
    <span className="font-mono text-[0.67rem] text-muted-foreground uppercase tracking-[0.16em]">
      {children}
    </span>
  );
}

export function SheetToolbar({
  books,
  chapters,
  filters,
  onFilterChange,
  defaultFormats,
  onDefaultFormatsChange,
  selectedCount,
  onFill,
  onClearAll,
}: {
  books: readonly BookSummary[];
  chapters: readonly SheetChapter[];
  filters: SheetFilters;
  onFilterChange: (patch: Partial<SheetFilters>) => void;
  defaultFormats: readonly QuestionType[];
  onDefaultFormatsChange: (formats: QuestionType[]) => void;
  selectedCount: number;
  onFill: (pattern: FillPattern) => void;
  onClearAll: () => void;
}) {
  return (
    <div className="flex flex-col gap-4 border-border/70 border-b bg-background/55 p-4">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <div className="space-y-1.5">
          <FieldLabel>Book</FieldLabel>
          <Select
            value={filters.bookId === null ? "all" : String(filters.bookId)}
            onValueChange={(value) =>
              onFilterChange({
                bookId: value === "all" ? null : Number(value),
                // A chapter belongs to one book, so it cannot survive the switch.
                chapterId: null,
              })
            }
          >
            <SelectTrigger className="h-9 w-full border-border/80 bg-background/85" size="sm">
              <SelectValue placeholder="Every book" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Every book ({books.length})</SelectItem>
              {books.map((book) => (
                <SelectItem key={book.id} value={String(book.id)}>
                  {book.title}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <FieldLabel>Chapter</FieldLabel>
          <Select
            value={filters.chapterId === null ? "all" : String(filters.chapterId)}
            onValueChange={(value) =>
              onFilterChange({ chapterId: value === "all" ? null : Number(value) })
            }
          >
            <SelectTrigger className="h-9 w-full border-border/80 bg-background/85" size="sm">
              <SelectValue placeholder="Any chapter" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Any chapter</SelectItem>
              {chapters.map((chapter) => (
                <SelectItem key={chapter.id} value={String(chapter.id)}>
                  {chapter.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <FieldLabel>Already produced</FieldLabel>
          <Select
            value={filters.produced}
            onValueChange={(value) =>
              onFilterChange({ produced: value as SheetFilters["produced"] })
            }
          >
            <SelectTrigger className="h-9 w-full border-border/80 bg-background/85" size="sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="any">Any chunk</SelectItem>
              <SelectItem value="none">No questions yet</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <FieldLabel>Search</FieldLabel>
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={filters.search}
              onChange={(event) => onFilterChange({ search: event.target.value })}
              placeholder="Chunk, chapter or book..."
              className="h-9 border-border/80 bg-background/85 pl-9"
            />
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <FieldLabel>Sheet default</FieldLabel>
        <FormatPicker value={defaultFormats} onChange={onDefaultFormatsChange} />
        <span className="text-muted-foreground text-xs">
          Every row follows this until you give it formats of its own. Each count is made in every
          chosen format, so two formats is twice the questions.
        </span>

        <span className="ml-auto flex flex-wrap items-center gap-2">
          <FieldLabel>Fill selected</FieldLabel>
          {FILLS.map((fill) => (
            <Button
              key={fill.label}
              type="button"
              variant="outline"
              size="sm"
              className="h-7 border-border/80 px-2.5 text-xs"
              disabled={selectedCount === 0}
              onClick={() => onFill(fill.pattern)}
            >
              {fill.label}
            </Button>
          ))}
          <span className="font-mono text-[0.67rem] text-muted-foreground tabular-nums">
            {selectedCount} selected
          </span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-muted-foreground text-xs"
            onClick={onClearAll}
          >
            <Eraser className="size-3" /> Reset sheet
          </Button>
        </span>
      </div>
    </div>
  );
}
