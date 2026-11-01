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
  selectedIds: ReadonlySet<string>;
  /** Rows that ask for at least one question. */
  specifiedCount: number;
  specFor: (chunkId: string) => ChunkSpec;
  setCount: (chunkId: string, difficulty: Difficulty, value: number) => void;
  setFormats: (chunkId: string, formats: QuestionType[] | null) => void;
  toggleSelected: (chunkId: string) => void;
  selectMany: (chunkIds: readonly string[], selected: boolean) => void;
  fillSelected: (pattern: FillPattern) => void;
  clearAll: () => void;
}

export function useChunkSpecs(): ChunkSpecsApi {
  const [specs, setSpecs] = useState<ChunkSpecMap>({});
  const [selectedIds, setSelectedIds] = useState<ReadonlySet<string>>(new Set());

  const specFor = useCallback(
    (chunkId: string): ChunkSpec => specs[chunkId] ?? EMPTY_SPEC,
    [specs],
  );

  const setCount = useCallback((chunkId: string, difficulty: Difficulty, value: number) => {
    setSpecs((current) => {
      const spec = current[chunkId] ?? EMPTY_SPEC;
      return { ...current, [chunkId]: { ...spec, [difficulty]: Math.max(0, value) } };
    });
  }, []);

  const setFormats = useCallback((chunkId: string, formats: QuestionType[] | null) => {
    setSpecs((current) => {
      const spec = current[chunkId] ?? EMPTY_SPEC;
      // An empty override is meaningless — a chunk with no format cannot be
      // generated from — so clearing every format falls back to inheriting.
      return {
        ...current,
        [chunkId]: { ...spec, formats: formats && formats.length > 0 ? formats : null },
      };
    });
  }, []);

  const toggleSelected = useCallback((chunkId: string) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (!next.delete(chunkId)) next.add(chunkId);
      return next;
    });
  }, []);

  const selectMany = useCallback((chunkIds: readonly string[], selected: boolean) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      for (const chunkId of chunkIds) {
        if (selected) next.add(chunkId);
        else next.delete(chunkId);
      }
      return next;
    });
  }, []);

  const fillSelected = useCallback(
    (pattern: FillPattern) => {
      setSpecs((current) => {
        const next = { ...current };
        for (const chunkId of selectedIds) {
          next[chunkId] = { ...(next[chunkId] ?? EMPTY_SPEC), ...pattern };
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
