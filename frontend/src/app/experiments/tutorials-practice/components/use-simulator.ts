"use client";

/**
 * State of the step-through simulator: which program is loaded, where the student is in its trace,
 * and the edit / re-run cycle of "Try it yourself". Presentational code lives in `simulator-sheet`.
 */

import { useCallback, useMemo, useState } from "react";
import { type RunResult, runProgram } from "../mini-python";

export type SimulatorMode = "watch" | "edit";

/** One plain sentence for a result that produced no trace at all (bad syntax, unsupported syntax). */
export function describeFailure(result: RunResult): string | null {
  if (result.steps.length > 0) return null;
  if (result.status === "syntax" && result.error) {
    return `${result.error.name}: ${result.error.message} (line ${result.error.line}). ${result.error.plain}`;
  }
  if (result.status === "unsupported") return result.message;
  return null;
}

export function useSimulator(initialCode: string) {
  const [source, setSource] = useState(initialCode);
  const [draft, setDraft] = useState(initialCode);
  const [mode, setMode] = useState<SimulatorMode>("watch");
  const [index, setIndex] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);

  const result = useMemo(() => runProgram(source), [source]);
  const last = Math.max(result.steps.length - 1, 0);

  const step = useCallback(() => setIndex((i) => Math.min(i + 1, last)), [last]);
  const back = useCallback(() => setIndex((i) => Math.max(i - 1, 0)), []);
  const reset = useCallback(() => setIndex(0), []);
  const toEnd = useCallback(() => setIndex(last), [last]);

  const startEditing = useCallback(() => {
    setDraft(source);
    setNotice(null);
    setMode("edit");
  }, [source]);

  const stopEditing = useCallback(() => {
    setNotice(null);
    setMode("watch");
  }, []);

  /** Run the draft: on success the student watches the new trace from its first line. */
  const runDraft = useCallback(() => {
    const next = runProgram(draft);
    const failure = describeFailure(next);
    if (failure) {
      setNotice(failure);
      return;
    }
    setSource(draft);
    setIndex(0);
    setNotice(null);
    setMode("watch");
  }, [draft]);

  const restoreOriginal = useCallback(() => {
    setSource(initialCode);
    setDraft(initialCode);
    setIndex(0);
    setNotice(null);
  }, [initialCode]);

  return {
    source,
    draft,
    setDraft,
    mode,
    index,
    last,
    result,
    notice,
    edited: source !== initialCode,
    step,
    back,
    reset,
    toEnd,
    startEditing,
    stopEditing,
    runDraft,
    restoreOriginal,
  };
}
