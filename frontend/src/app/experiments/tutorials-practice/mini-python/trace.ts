/** Reading a `RunResult` for display: captions, changed variables, the line sequence. */

import type { RunResult, Step, VarSnap } from "./types";

/** The line numbers of the 'line' steps, in order: what the CPython table test compares. */
export function lineSequence(result: RunResult): number[] {
  return result.steps.filter((s) => s.kind === "line").map((s) => s.line as number);
}

/**
 * The plain-words caption for step `index`. The state on screen is the state BEFORE that step's line
 * runs, so the caption explains what the previous line just did.
 */
export function captionFor(steps: Step[], index: number): string {
  const step = steps[index];
  if (!step) return "";
  if (step.kind === "limit" || step.kind === "unsupported" || step.kind === "error") {
    return step.message ?? "";
  }
  const parts: string[] = [];
  const previous = steps[index - 1];
  if (previous) parts.push(...previous.after);
  if (step.entered) parts.push(`Called \`${step.entered}\`: a new frame is added.`);
  if (step.kind === "end") parts.push("The program finished.");
  else if (index === 0) parts.push(`Line ${step.line} runs first.`);
  return parts.join(" ");
}

/** Variables whose value differs from the previous step (same frame position, same name). */
export function changedVars(steps: Step[], index: number): Set<string> {
  const changed = new Set<string>();
  const step = steps[index];
  const previous = steps[index - 1];
  if (!step) return changed;
  step.frames.forEach((frame, frameIndex) => {
    const before = previous?.frames[frameIndex];
    const same = before && before.label === frame.label;
    for (const v of frame.vars) {
      const old: VarSnap | undefined = same
        ? before.vars.find((x) => x.name === v.name)
        : undefined;
      if (!old || old.repr !== v.repr) changed.add(`${frameIndex}:${v.name}`);
    }
  });
  return changed;
}

/**
 * Printed output made short enough to sit next to a chosen answer: a line repeated many times in a
 * row becomes `line  (x N)`.
 */
export function condenseOutput(output: string): string {
  const lines = output.split("\n");
  if (lines[lines.length - 1] === "") lines.pop();
  const out: string[] = [];
  let i = 0;
  while (i < lines.length) {
    let j = i;
    while (j < lines.length && lines[j] === lines[i]) j++;
    const run = j - i;
    if (run >= 4) out.push(`${lines[i]}  (x${run})`);
    else for (let k = i; k < j; k++) out.push(lines[k]);
    i = j;
  }
  return out.join("\n");
}
