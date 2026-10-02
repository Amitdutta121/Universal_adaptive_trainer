"use client";

/**
 * The state of one trace being stepped through: which step it is on, and the auto-play clock.
 *
 * Auto-play rules: it only ever starts from the Play button, it stops on its own at the last step,
 * and it stops the moment the window loses focus, the tab is hidden, or the student's device asks
 * for reduced motion (in which case Play is unavailable and stepping stays manual).
 */

import { useCallback, useEffect, useState } from "react";
import type { Trace } from "../mock-data";

/** Milliseconds between steps while playing. */
export const PLAY_DELAY_MS = { slow: 1400, fast: 600 } as const;

function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(query.matches);
    const handler = (event: MediaQueryListEvent) => setReduced(event.matches);
    query.addEventListener("change", handler);
    return () => query.removeEventListener("change", handler);
  }, []);
  return reduced;
}

export function useTraceRunner(trace: Trace) {
  const total = trace.steps.length;
  /** 0 = nothing has run yet; n = the first n steps have run. */
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [fast, setFast] = useState(false);
  const reducedMotion = useReducedMotion();
  const atEnd = index >= total;

  const step = useCallback(() => setIndex((current) => Math.min(current + 1, total)), [total]);
  const reset = useCallback(() => {
    setPlaying(false);
    setIndex(0);
  }, []);
  const jumpToEnd = useCallback(() => {
    setPlaying(false);
    setIndex(total);
  }, [total]);
  const togglePlay = useCallback(() => {
    if (reducedMotion) return;
    if (playing) {
      setPlaying(false);
      return;
    }
    if (atEnd) setIndex(0);
    setPlaying(true);
  }, [reducedMotion, playing, atEnd]);

  // The clock. It runs only while `playing`, and playing ends by itself at the last step.
  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(step, fast ? PLAY_DELAY_MS.fast : PLAY_DELAY_MS.slow);
    return () => window.clearInterval(timer);
  }, [playing, fast, step]);

  useEffect(() => {
    if (atEnd) setPlaying(false);
  }, [atEnd]);

  // Losing focus pauses; nothing resumes on its own.
  useEffect(() => {
    if (!playing) return;
    const pause = () => setPlaying(false);
    const onVisibility = () => {
      if (document.hidden) pause();
    };
    window.addEventListener("blur", pause);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.removeEventListener("blur", pause);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [playing]);

  useEffect(() => {
    if (reducedMotion) setPlaying(false);
  }, [reducedMotion]);

  return {
    index,
    total,
    atEnd,
    playing,
    fast,
    reducedMotion,
    step,
    reset,
    jumpToEnd,
    togglePlay,
    setFast,
  };
}

export type TraceRunner = ReturnType<typeof useTraceRunner>;
