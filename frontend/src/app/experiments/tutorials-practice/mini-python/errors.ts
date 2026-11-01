/** Errors raised while lexing, parsing and running. None of them ever escapes `runProgram`. */

import type { FrameSnap } from "./types";

/** The code is not valid Python (or not valid indentation). Raised before anything runs. */
export class SyntaxIssue extends Error {
  constructor(
    readonly errorName: "SyntaxError" | "IndentationError",
    message: string,
    readonly line: number,
  ) {
    super(message);
  }
}

/** Valid Python that this mini-runner does not implement. `feature` completes "doesn't support ...". */
export class UnsupportedError extends Error {
  constructor(
    readonly feature: string,
    readonly line: number,
  ) {
    super(feature);
  }
}

/** A Python exception raised while running, carrying the state at the moment it was raised. */
export class PyError extends Error {
  frames: FrameSnap[] = [];
  output = "";
  constructor(
    readonly errorName: string,
    message: string,
    readonly plain: string,
    public line: number,
  ) {
    super(message);
  }
}

/** The step budget ran out. */
export class StepLimitReached extends Error {
  constructor(readonly line: number) {
    super("step limit");
  }
}
