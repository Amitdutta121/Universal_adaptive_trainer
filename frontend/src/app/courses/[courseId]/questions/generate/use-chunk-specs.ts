"use client";

/**
 * The spec sheet's own state: what each chunk asks for, and which rows are selected.
 *
 * This is browser state, not server state — an unsubmitted form. It stays out of
 * the URL because a sheet of forty chunks does not belong in a query string, and
 * out of TanStack Query because nothing on the server knows about it until the run
 * is submitted.
 *
 * Two ideas are worth keeping straight:
 *
 * - *Selection* is what the bulk actions write to. It does not decide what runs.
 * - *Counts* are what runs. A row with counts is in the run whether or not it is
 *   selected, which is what makes the totals answer "what will happen" rather than
 *   "what is highlighted".
 */

import { useCallback, useMemo, useState } from "react";
import type { Difficulty, QuestionType } from "@/lib/api/types";
import {
  type ChunkSpec,
  type ChunkSpecMap,
  EMPTY_SPEC,
  specPerFormatTotal,
} from "./spec-sheet-types";

/** A bulk fill: the counts to write into every selected row. */
export interface FillPattern {
  easy: number;
  medium: number;
  hard: number;
}

export interface ChunkSpecsApi {
  specs: ChunkSpecMap;
  selectedIds: ReadonlySet<number>;
  /** Rows that ask for at least one question. */
  specifiedCount: number;
  specFor: (sectionId: number) => ChunkSpec;
  setCount: (sectionId: number, difficulty: Difficulty, value: number) => void;
  setFormats: (sectionId: number, formats: QuestionType[] | null) => void;
  toggleSelected: (sectionId: number) => void;
  selectMany: (sectionIds: readonly number[], selected: boolean) => void;
  fillSelected: (pattern: FillPattern) => void;
  clearAll: () => void;
}

export function useChunkSpecs(): ChunkSpecsApi {
  const [specs, setSpecs] = useState<ChunkSpecMap>({});
  const [selectedIds, setSelectedIds] = useState<ReadonlySet<number>>(new Set());

  const specFor = useCallback(
    (sectionId: number): ChunkSpec => specs[sectionId] ?? EMPTY_SPEC,
    [specs],
  );

  const setCount = useCallback((sectionId: number, difficulty: Difficulty, value: number) => {
    setSpecs((current) => {
      const spec = current[sectionId] ?? EMPTY_SPEC;
      return { ...current, [sectionId]: { ...spec, [difficulty]: Math.max(0, value) } };
    });
  }, []);

  const setFormats = useCallback((sectionId: number, formats: QuestionType[] | null) => {
    setSpecs((current) => {
      const spec = current[sectionId] ?? EMPTY_SPEC;
      // An empty override is meaningless — a chunk with no format cannot be
      // generated from — so clearing every format falls back to inheriting.
      return {
        ...current,
        [sectionId]: { ...spec, formats: formats && formats.length > 0 ? formats : null },
      };
    });
  }, []);

  const toggleSelected = useCallback((sectionId: number) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (!next.delete(sectionId)) next.add(sectionId);
      return next;
    });
  }, []);

  const selectMany = useCallback((sectionIds: readonly number[], selected: boolean) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      for (const sectionId of sectionIds) {
        if (selected) next.add(sectionId);
        else next.delete(sectionId);
      }
      return next;
    });
  }, []);

  const fillSelected = useCallback(
    (pattern: FillPattern) => {
      setSpecs((current) => {
        const next = { ...current };
        for (const sectionId of selectedIds) {
          next[sectionId] = { ...(next[sectionId] ?? EMPTY_SPEC), ...pattern };
        }
        return next;
      });
    },
    [selectedIds],
  );

  const clearAll = useCallback(() => {
    setSpecs({});
    setSelectedIds(new Set());
  }, []);

  const specifiedCount = useMemo(
    () => Object.values(specs).filter((spec) => specPerFormatTotal(spec) > 0).length,
    [specs],
  );

  return {
    specs,
    selectedIds,
    specifiedCount,
    specFor,
    setCount,
    setFormats,
    toggleSelected,
    selectMany,
    fillSelected,
    clearAll,
  };
}
