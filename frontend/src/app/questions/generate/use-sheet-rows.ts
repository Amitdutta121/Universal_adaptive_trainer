"use client";

/**
 * The row model: several books' generation plans, flattened into one table.
 *
 * The plan endpoint answers per book, so this hook asks for one plan per book and
 * merges them. Nothing here decides anything about generation — a row carries what
 * the plan said about a chunk, plus the book and chapter it came from, which the
 * per-book response leaves implicit.
 */

import { useMemo } from "react";
import { useBooks, useGenerationPlans } from "@/lib/api/queries";
import type { BookSummary, SheetRow } from "./spec-sheet-types";

export interface SheetFilters {
  bookId: number | null;
  chapterId: number | null;
  /** "any" | "none" — chunks that have produced no question yet. */
  produced: "any" | "none";
  search: string;
}

export interface SheetChapter {
  id: number;
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

  // Narrowing to one book asks for one plan, not all of them: a professor working
  // in a single book should not pay for every other book's plan on every load.
  const bookIds = useMemo(
    () =>
      filters.bookId !== null
        ? books.filter((book) => book.id === filters.bookId).map((book) => book.id)
        : books.map((book) => book.id),
    [books, filters.bookId],
  );

  const plans = useGenerationPlans(bookIds);

  const allRows = useMemo<SheetRow[]>(
    () =>
      plans.plans.flatMap((plan) =>
        plan.chapters.flatMap((chapter) =>
          chapter.sections.map((entry) => ({
            sectionId: entry.section.id,
            bookId: plan.book.id,
            bookTitle: plan.book.title,
            chapterId: chapter.id,
            chapterLabel: chapter.label,
            title: entry.section.display_title,
            locationLabel: entry.section.location_label,
            charCount: entry.section.char_count,
            existingQuestionCount: entry.existing_question_count,
            selectable: entry.selectable,
            isUnlabelled: entry.section.is_unlabelled,
          })),
        ),
      ),
    [plans.plans],
  );

  const chapters = useMemo<SheetChapter[]>(() => {
    const seen = new Map<number, SheetChapter>();
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
    isPending: booksQuery.isPending || plans.isPending,
    isError: booksQuery.isError || plans.isError,
    error: booksQuery.error ?? plans.error,
  };
}
