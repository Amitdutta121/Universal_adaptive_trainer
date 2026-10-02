/**
 * The sheet's own state.
 *
 * The behaviours pinned here are the ones a professor would notice if they broke:
 * a bulk fill writes only to selected rows, clearing every format goes back to
 * inheriting rather than leaving a chunk with none, and counts never go negative.
 */

import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useChunkSpecs } from "./use-chunk-specs";

describe("useChunkSpecs", () => {
  it("starts with nothing specified", () => {
    const { result } = renderHook(() => useChunkSpecs());

    expect(result.current.specifiedCount).toBe(0);
    expect(result.current.specFor(1)).toEqual({ easy: 0, medium: 0, hard: 0, formats: null });
  });

  it("counts a chunk as specified once it asks for a question", () => {
    const { result } = renderHook(() => useChunkSpecs());

    act(() => result.current.setCount(1, "medium", 2));

    expect(result.current.specFor(1).medium).toBe(2);
    expect(result.current.specifiedCount).toBe(1);
  });

  it("never lets a count go below zero", () => {
    const { result } = renderHook(() => useChunkSpecs());

    act(() => result.current.setCount(1, "easy", -3));

    expect(result.current.specFor(1).easy).toBe(0);
  });

  it("fills only the selected rows", () => {
    const { result } = renderHook(() => useChunkSpecs());

    act(() => result.current.selectMany([1, 2], true));
    act(() => result.current.fillSelected({ easy: 1, medium: 1, hard: 1 }));

    expect(result.current.specFor(1).hard).toBe(1);
    expect(result.current.specFor(2).hard).toBe(1);
    expect(result.current.specFor(3).hard).toBe(0);
  });

  it("keeps a row's formats when a fill rewrites its counts", () => {
    const { result } = renderHook(() => useChunkSpecs());

    act(() => result.current.setFormats(1, ["coding"]));
    act(() => result.current.selectMany([1], true));
    act(() => result.current.fillSelected({ easy: 2, medium: 0, hard: 0 }));

    expect(result.current.specFor(1)).toMatchObject({ easy: 2, formats: ["coding"] });
  });

  it("goes back to inheriting when every format is cleared", () => {
    const { result } = renderHook(() => useChunkSpecs());

    act(() => result.current.setFormats(1, ["coding"]));
    act(() => result.current.setFormats(1, []));

    expect(result.current.specFor(1).formats).toBeNull();
  });

  it("toggles one row's selection without touching the others", () => {
    const { result } = renderHook(() => useChunkSpecs());

    act(() => result.current.selectMany([1, 2], true));
    act(() => result.current.toggleSelected(1));

    expect([...result.current.selectedIds]).toEqual([2]);
  });

  it("resets the whole sheet", () => {
    const { result } = renderHook(() => useChunkSpecs());

    act(() => result.current.setCount(1, "hard", 2));
    act(() => result.current.selectMany([1], true));
    act(() => result.current.clearAll());

    expect(result.current.specifiedCount).toBe(0);
    expect(result.current.selectedIds.size).toBe(0);
  });
});
