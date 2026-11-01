"use client";

/**
 * The row model: several books' chunk outlines, flattened into one table.
 *
 * The outline endpoint answers per book, so this hook asks for one outline per book and
 * merges them. Nothing here decides anything about generation. A chunk's chapter is its
 * top-level heading, or the book's title when it has none, numbered in reading order.
 */

import { useMemo } from "react";
import { useBooks, useChunkOutlines } from "@/lib/api/queries";
import type { BookSummary, SheetRow } from "./spec-sheet-types";

export interface SheetFilters {
  bookId: number | null;
  chapterId: string | null;
  /** "any" | "none" — chunks that have produced no question yet. */
  produced: "any" | "none";
  search: string;
}

export interface SheetChapter {
  id: string;
  label: string;
  bookTitle: string;
}

export interface SheetRowsApi {
  books: readonly BookSummary[];
  chapters: readonly SheetChapter[];
  /** Every chunk across every book, unfiltered — what the totals are drawn from. */
  allRows: readonly SheetRow[];
  /** What the table shows: `allRows` narrowed by the active filters. */
  rows: readonly SheetRow[];
  isPending: boolean;
  isError: boolean;
  error: unknown;
}

export function useSheetRows(filters: SheetFilters): SheetRowsApi {
  const booksQuery = useBooks();
  const books = useMemo(() => booksQuery.data?.books ?? [], [booksQuery.data]);

  // Narrowing to one book asks for one outline, not all of them: a professor working
  // in a single book should not pay for every other book's outline on every load.
  const bookIds = useMemo(
    () =>
      filters.bookId !== null
        ? books.filter((book) => book.id === filters.bookId).map((book) => book.id)
        : books.map((book) => book.id),
    [books, filters.bookId],
  );

  const plans = useChunkOutlines(bookIds);

  const allRows = useMemo<SheetRow[]>(
    () =>
      plans.outlines.flatMap((outline) => {
        const chapterIndex = new Map<string, number>();
        return outline.chunks.map((entry) => {
          const chapterLabel = entry.chunk.heading_path[0] ?? outline.book.title;
          if (!chapterIndex.has(chapterLabel)) chapterIndex.set(chapterLabel, chapterIndex.size);
          return {
            chunkId: entry.chunk.id,
            bookId: outline.book.id,
            bookTitle: outline.book.title,
            chapterId: `${outline.book.id}:${chapterIndex.get(chapterLabel)}`,
            chapterLabel,
            title: entry.chunk.label,
            locationLabel: entry.chunk.location_label,
            charCount: entry.chunk.char_count,
            startPage: entry.chunk.page_start,
            endPage: entry.chunk.page_end,
            existingQuestionCount: entry.existing_question_count,
            selectable: entry.chunk.char_count > 0,
            isUnlabelled: entry.chunk.heading_path.length === 0,
          };
        });
      }),
    [plans.outlines],
  );

  const chapters = useMemo<SheetChapter[]>(() => {
    const seen = new Map<string, SheetChapter>();
    for (const row of allRows) {
      if (!seen.has(row.chapterId)) {
        seen.set(row.chapterId, {
          id: row.chapterId,
          label: row.chapterLabel,
          bookTitle: row.bookTitle,
        });
      }
    }
    return [...seen.values()];
  }, [allRows]);

  const rows = useMemo(() => {
    const needle = filters.search.trim().toLowerCase();
    return allRows.filter((row) => {
      if (filters.chapterId !== null && row.chapterId !== filters.chapterId) return false;
      if (filters.produced === "none" && row.existingQuestionCount > 0) return false;
      if (!needle) return true;
      return [row.title, row.bookTitle, row.chapterLabel, row.locationLabel]
        .filter((value): value is string => Boolean(value))
        .join(" ")
        .toLowerCase()
        .includes(needle);
    });
  }, [allRows, filters.chapterId, filters.produced, filters.search]);

  return {
    books,
    chapters,
    allRows,
    rows,
    // In the render where the books arrive, the outline queries have not been created yet and
    // report "not pending" with no rows; treating that as loaded made a deep-linked chunk look
    // stale and get dropped.
    isPending:
      booksQuery.isPending ||
      plans.isPending ||
      (!plans.isError && plans.outlines.length < bookIds.length),
    isError: booksQuery.isError || plans.isError,
    error: booksQuery.error ?? plans.error,
  };
}
