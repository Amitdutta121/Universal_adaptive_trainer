"use client";

/**
 * The state of one trace being stepped through, including the optional predict-first gates.
 *
 * `index` is the step on screen (0 = nothing has run). A prediction is asked when the student
 * presses Step to reveal `prediction.atStep`, and only while prediction is on. Answering (or
 * "Just show me", which also turns prediction off) reveals that step. There is no auto-play.
 */

import { useCallback, useState } from "react";
import type { Prediction, Trace } from "../traces.generated";

export type PredictionResult = { prediction: Prediction; choice: number; correct: boolean };

export function useTraceRunner(
  trace: Trace,
  predictOn: boolean,
  setPredictOn: (on: boolean) => void,
) {
  const last = trace.steps.length - 1;
  const [index, setIndex] = useState(0);
  const [asking, setAsking] = useState<Prediction | null>(null);
  const [results, setResults] = useState<Record<string, PredictionResult>>({});

  const step = useCallback(() => {
    if (asking || index >= last) return;
    const next = index + 1;
    const gate = predictOn
      ? trace.predictions.find((p) => p.atStep === next && !results[p.id])
      : undefined;
    if (gate) setAsking(gate);
    else setIndex(next);
  }, [asking, index, last, predictOn, results, trace.predictions]);

  const back = useCallback(() => {
    setAsking(null);
    setIndex((current) => Math.max(0, current - 1));
  }, []);

  const reset = useCallback(() => {
    setAsking(null);
    setResults({});
    setIndex(0);
  }, []);

  const answer = useCallback(
    (choice: number) => {
      if (!asking) return;
      setResults((current) => ({
        ...current,
        [asking.id]: { prediction: asking, choice, correct: choice === asking.answer },
      }));
      setIndex(asking.atStep);
      setAsking(null);
    },
    [asking],
  );

  const justShowMe = useCallback(() => {
    setPredictOn(false);
    if (asking) {
      setIndex(asking.atStep);
      setAsking(null);
    }
  }, [asking, setPredictOn]);

  /** The answer the student gave to the question that revealed the step on screen, if any. */
  const feedback = Object.values(results).find((r) => r.prediction.atStep === index) ?? null;

  return {
    index,
    last,
    atEnd: index >= last,
    current: trace.steps[index],
    previous: index > 0 ? trace.steps[index - 1] : undefined,
    asking,
    feedback,
    step,
    back,
    reset,
    answer,
    justShowMe,
  };
}
