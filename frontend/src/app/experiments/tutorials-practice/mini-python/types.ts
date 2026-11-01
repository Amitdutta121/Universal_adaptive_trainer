/**
 * Shared types of the mini Python runner: tokens, the syntax tree, and the recorded trace.
 *
 * TODO(real): this whole `mini-python/` folder is a prototype stand-in. The real system would run
 * the student's code in a sandbox (Pyodide in the browser, or a server) and record the trace from
 * CPython itself; the `Step` shape below is what such a recorder would have to produce.
 */

// ---- tokens ---------------------------------------------------------------------------------

export type TokenType =
  | "NAME"
  | "NUMBER"
  | "STRING"
  | "OP"
  | "NEWLINE"
  | "INDENT"
  | "DEDENT"
  | "EOF";

export interface Token {
  type: TokenType;
  /** The source text; for STRING the already-unescaped value. */
  text: string;
  /** 1-based physical line the token starts on. */
  line: number;
  /** Offsets into the (newline-normalised) source, for quoting a piece of code back. */
  start: number;
  end: number;
}

// ---- syntax tree ----------------------------------------------------------------------------

export type Expr =
  | { k: "num"; v: bigint | number; line: number }
  | { k: "str"; v: string; line: number }
  | { k: "const"; v: boolean | null; line: number }
  | { k: "name"; id: string; line: number }
  | { k: "list"; items: Expr[]; line: number }
  | { k: "unary"; op: "-" | "+" | "not"; e: Expr; line: number }
  | { k: "bin"; op: "+" | "-" | "*" | "/" | "//" | "%" | "**"; l: Expr; r: Expr; line: number }
  | { k: "logic"; op: "and" | "or"; l: Expr; r: Expr; line: number }
  | { k: "cmp"; first: Expr; rest: { op: CompareOp; e: Expr }[]; line: number }
  | { k: "call"; fn: Expr; args: Expr[]; line: number }
  | { k: "method"; obj: Expr; objText: string; name: string; args: Expr[]; line: number }
  | { k: "index"; obj: Expr; idx: Expr; line: number };

export type CompareOp = "==" | "!=" | "<" | "<=" | ">" | ">=" | "in" | "not in" | "is" | "is not";

export type AugOp = "+" | "-" | "*" | "/" | "//" | "%";

export type Target =
  | { k: "name"; id: string; text: string }
  | { k: "index"; obj: Expr; idx: Expr; text: string };

export type Stmt =
  | { k: "expr"; e: Expr; line: number }
  | { k: "assign"; targets: Target[]; value: Expr; line: number }
  | { k: "aug"; target: Target; op: AugOp; value: Expr; line: number }
  | { k: "if"; test: Expr; testText: string; body: Stmt[]; orelse: Stmt[]; line: number }
  | { k: "while"; test: Expr; testText: string; body: Stmt[]; line: number }
  | { k: "for"; varName: string; iter: Expr; body: Stmt[]; line: number }
  | {
      k: "def";
      name: string;
      params: string[];
      /** Names assigned anywhere in the body (plus the parameters): Python treats these as local. */
      localNames: string[];
      body: Stmt[];
      line: number;
    }
  | { k: "return"; value: Expr | null; line: number }
  | { k: "break"; line: number }
  | { k: "continue"; line: number }
  | { k: "pass"; line: number };

// ---- the trace ------------------------------------------------------------------------------

export interface VarSnap {
  name: string;
  /** Python type name: int, float, str, bool, NoneType, list, range, function. */
  type: string;
  /** What `repr()` would show. */
  repr: string;
  /** Lists only: identity, so two names holding the same list are visibly the same. */
  listId?: number;
}

export interface FrameSnap {
  /** "Global" for the module, else e.g. `fact(3)`. */
  label: string;
  isModule: boolean;
  vars: VarSnap[];
}

/**
 * One step. For a "line" step the state is what it is JUST BEFORE `line` runs (the marker sits on
 * the line about to run, as in Python Tutor). `after` holds the plain-words effects that completed
 * between this step and the next, so the caption for step N is `steps[N - 1].after`.
 */
export interface Step {
  kind: "line" | "end" | "error" | "limit" | "unsupported";
  /** 1-based source line to highlight; null on a normal end. */
  line: number | null;
  frames: FrameSnap[];
  /** Everything printed so far. */
  output: string;
  after: string[];
  /** Set on the first line of a function call: e.g. `fact(3)`. */
  entered?: string;
  /** Terminal steps other than "end": the plain-words text shown as the caption. */
  message?: string;
}

export type RunStatus = "ok" | "error" | "limit" | "unsupported" | "syntax";

export interface RunError {
  /** The name Python gives it: NameError, IndexError, ... */
  name: string;
  /** CPython's own message text. */
  message: string;
  /** One line in plain words. */
  plain: string;
  line: number;
}

export interface RunResult {
  status: RunStatus;
  steps: Step[];
  /** Final stdout. */
  output: string;
  /** Plain-words explanation for limit / unsupported results; null otherwise. */
  message: string | null;
  error: RunError | null;
}

export interface RunLimits {
  maxSteps: number;
  maxDepth: number;
}

export const DEFAULT_LIMITS: RunLimits = { maxSteps: 300, maxDepth: 20 };
