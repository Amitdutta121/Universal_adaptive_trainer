/**
 * Evaluator + tracer for the teaching subset of Python. A tree-walking interpreter: no `eval`, no
 * `Function`, no dependencies, and hard caps (steps, call depth, value size) so a student's runaway
 * loop or recursion always ends with a plain-words message instead of freezing the tab.
 *
 * One STEP is one CPython 'line' event: recorded when a line is about to run (statements, `if` /
 * `elif` / `while` tests, each `for` iteration). The table test compares the sequence of those line
 * numbers against real CPython. See `cpython-table.test.ts`.
 */

import { PyError, StepLimitReached, SyntaxIssue, UnsupportedError } from "./errors";
import { parseProgram } from "./parser";
import {
  DEFAULT_LIMITS,
  type Expr,
  type FrameSnap,
  type RunError,
  type RunLimits,
  type RunResult,
  type Stmt,
  type Step,
  type Target,
} from "./types";
import {
  equals,
  isNumeric,
  isObject,
  type PyFunction,
  type PyList,
  type PyRange,
  rangeLength,
  repr,
  str,
  toNum,
  truthy,
  type Value,
  typeName,
} from "./values";

const MAX_SOURCE_CHARS = 5000;
/** Longest list / string a program may build (`"a" * 10**9` must not freeze the tab). */
const MAX_VALUE_SIZE = 10_000;

const BUILTINS = new Set([
  "print",
  "range",
  "len",
  "str",
  "int",
  "float",
  "bool",
  "abs",
  "sum",
  "min",
  "max",
  "list",
]);

/** Real Python builtins we do not implement: named as unsupported instead of "not defined". */
const UNSUPPORTED_BUILTINS = new Set([
  "sorted",
  "reversed",
  "enumerate",
  "zip",
  "map",
  "filter",
  "input",
  "open",
  "type",
  "isinstance",
  "dict",
  "set",
  "tuple",
  "round",
  "pow",
  "divmod",
  "any",
  "all",
  "chr",
  "ord",
  "format",
  "id",
  "hash",
  "iter",
  "next",
  "repr",
  "callable",
  "getattr",
  "setattr",
  "hasattr",
  "dir",
  "eval",
  "exec",
  "object",
  "super",
  "slice",
  "frozenset",
  "bytes",
  "complex",
  "help",
  "exit",
  "quit",
]);

const LIST_METHODS = new Set(["append", "pop", "extend", "insert", "copy"]);
const UNSUPPORTED_LIST_METHODS = new Set(["sort", "reverse", "index", "count", "remove", "clear"]);
const STR_METHODS = new Set([
  "upper",
  "lower",
  "split",
  "join",
  "strip",
  "lstrip",
  "rstrip",
  "replace",
  "startswith",
  "endswith",
  "find",
  "format",
  "count",
  "title",
  "capitalize",
  "isdigit",
  "isalpha",
  "index",
  "center",
  "zfill",
  "splitlines",
  "swapcase",
  "isupper",
  "islower",
  "isspace",
  "rfind",
]);

type Signal = undefined | { t: "break" } | { t: "continue" } | { t: "return"; value: Value };

interface Frame {
  label: string;
  isModule: boolean;
  vars: Map<string, Value>;
  /** Names Python treats as local in this function; null for the module. */
  localNames: Set<string> | null;
}

const shorten = (text: string, max = 40): string =>
  text.length > max ? `${text.slice(0, max - 3)}...` : text;

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

class Machine {
  readonly frames: Frame[] = [
    { label: "Global", isModule: true, vars: new Map(), localNames: null },
  ];
  readonly steps: Step[] = [];
  output = "";
  private nextListId = 1;
  private pendingEntered: string | undefined;
  private line = 1;

  constructor(readonly limits: RunLimits) {}

  // ---- recording ----------------------------------------------------------------------------

  private get frame(): Frame {
    return this.frames[this.frames.length - 1];
  }

  snapshotFrames(): FrameSnap[] {
    return this.frames.map((frame) => ({
      label: frame.label,
      isModule: frame.isModule,
      vars: [...frame.vars].map(([name, value]) => ({
        name,
        type: typeName(value),
        repr: repr(value),
        ...(isObject(value) && value.kind === "list" ? { listId: value.id } : {}),
      })),
    }));
  }

  /** A CPython 'line' event: `line` is about to run. */
  mark(line: number): void {
    if (this.steps.length >= this.limits.maxSteps) throw new StepLimitReached(line);
    this.line = line;
    this.steps.push({
      kind: "line",
      line,
      frames: this.snapshotFrames(),
      output: this.output,
      after: [],
      ...(this.pendingEntered ? { entered: this.pendingEntered } : {}),
    });
    this.pendingEntered = undefined;
  }

  /** A plain-words effect that just completed; shown as the caption of the NEXT step. */
  private note(text: string): void {
    this.steps[this.steps.length - 1]?.after.push(text);
  }

  terminal(kind: Step["kind"], line: number | null, message?: string): Step {
    return {
      kind,
      line,
      frames: this.snapshotFrames(),
      output: this.output,
      after: [],
      ...(message ? { message } : {}),
    };
  }

  // ---- errors -------------------------------------------------------------------------------

  private fail(name: string, message: string, plain: string): never {
    const error = new PyError(name, message, plain, this.line);
    error.frames = this.snapshotFrames();
    error.output = this.output;
    throw error;
  }

  private typeError(message: string, plain?: string): never {
    return this.fail(
      "TypeError",
      message,
      plain ?? "These two values can't be used together this way. Check what type each one is.",
    );
  }

  private newList(items: Value[]): PyList {
    return { kind: "list", id: this.nextListId++, items };
  }

  private checkSize(n: number): void {
    if (n > MAX_VALUE_SIZE) {
      throw new UnsupportedError("building a value with more than 10,000 items", this.line);
    }
  }

  // ---- statements ---------------------------------------------------------------------------

  execBlock(body: Stmt[]): Signal {
    for (const stmt of body) {
      const signal = this.exec(stmt);
      if (signal) return signal;
    }
    return undefined;
  }

  private exec(s: Stmt): Signal {
    switch (s.k) {
      case "expr":
        this.mark(s.line);
        this.eval(s.e);
        return undefined;

      case "assign": {
        this.mark(s.line);
        const value = this.eval(s.value);
        for (const target of s.targets) this.assign(target, value);
        const first = s.targets[0];
        if (
          isObject(value) &&
          value.kind === "list" &&
          s.value.k === "name" &&
          first.k === "name"
        ) {
          this.note(
            `\`${first.text}\` now refers to the same list as \`${s.value.id}\` (list #${value.id}). Nothing was copied.`,
          );
        } else {
          this.note(`\`${first.text}\` is now ${shorten(repr(value))}.`);
        }
        return undefined;
      }

      case "aug": {
        this.mark(s.line);
        const target = s.target;
        const current = this.readTarget(target);
        const operand = this.eval(s.value);
        if (
          s.op === "+" &&
          isObject(current) &&
          current.kind === "list" &&
          isObject(operand) &&
          operand.kind === "list"
        ) {
          // `a += b` on a list extends the SAME list in place: this is what makes aliasing visible.
          const items = [...operand.items];
          this.checkSize(current.items.length + items.length);
          current.items.push(...items);
          this.assign(target, current);
          this.note(
            `\`${target.text}\` was extended in place: still list #${current.id}, now ${shorten(repr(current))}.`,
          );
        } else {
          const result = this.binary(s.op, current, operand);
          this.assign(target, result);
          this.note(`\`${target.text}\` is now ${shorten(repr(result))}.`);
        }
        return undefined;
      }

      case "if": {
        this.mark(s.line);
        const outcome = truthy(this.eval(s.test));
        this.note(
          outcome
            ? `\`${s.testText}\` is True: run this block.`
            : `\`${s.testText}\` is False: ${s.orelse.length > 0 ? "try the next branch" : "skip this block"}.`,
        );
        return this.execBlock(outcome ? s.body : s.orelse);
      }

      case "while": {
        for (;;) {
          this.mark(s.line);
          const outcome = truthy(this.eval(s.test));
          this.note(
            outcome
              ? `\`${s.testText}\` is True: run the loop body.`
              : `\`${s.testText}\` is False: leave the loop.`,
          );
          if (!outcome) return undefined;
          const signal = this.execBlock(s.body);
          if (signal?.t === "break") return undefined;
          if (signal?.t === "return") return signal;
        }
      }

      case "for": {
        this.mark(s.line);
        const iterable = this.eval(s.iter);
        const next = this.iterator(iterable);
        for (;;) {
          const item = next();
          if (item.done) {
            this.note("No items left: leave the loop.");
            return undefined;
          }
          this.frame.vars.set(s.varName, item.value);
          this.note(`\`${s.varName}\` is now ${shorten(repr(item.value))}.`);
          const signal = this.execBlock(s.body);
          if (signal?.t === "break") return undefined;
          if (signal?.t === "return") return signal;
          this.mark(s.line);
        }
      }

      case "def": {
        this.mark(s.line);
        const fn: PyFunction = {
          kind: "function",
          name: s.name,
          params: s.params,
          localNames: new Set(s.localNames),
          body: s.body,
        };
        this.frame.vars.set(s.name, fn);
        this.note(`\`${s.name}\` is defined. Its body does not run until it is called.`);
        return undefined;
      }

      case "return": {
        this.mark(s.line);
        const value = s.value ? this.eval(s.value) : null;
        this.note(`Return ${shorten(repr(value))} to the caller.`);
        return { t: "return", value };
      }

      case "break":
        this.mark(s.line);
        this.note("Leave the loop.");
        return { t: "break" };

      case "continue":
        this.mark(s.line);
        this.note("Skip to the next round of the loop.");
        return { t: "continue" };

      case "pass":
        this.mark(s.line);
        return undefined;
    }
  }

  private assign(target: Target, value: Value): void {
    if (target.k === "name") {
      this.frame.vars.set(target.id, value);
      return;
    }
    const obj = this.eval(target.obj);
    const idx = this.eval(target.idx);
    if (!isObject(obj) || obj.kind !== "list") {
      if (typeof obj === "string") {
        this.typeError(
          "'str' object does not support item assignment",
          "Strings can't be changed in place. Build a new string instead.",
        );
      }
      this.typeError(`'${typeName(obj)}' object does not support item assignment`);
    }
    const position = this.listPosition(
      obj.items.length,
      idx,
      "list assignment index out of range",
      "assign",
    );
    obj.items[position] = value;
  }

  private readTarget(target: Target): Value {
    if (target.k === "name") return this.lookup(target.id);
    return this.index(this.eval(target.obj), this.eval(target.idx));
  }

  // ---- iteration ----------------------------------------------------------------------------

  private iterator(v: Value): () => { done: true } | { done: false; value: Value } {
    if (isObject(v) && v.kind === "list") {
      let i = 0; // live: appending while looping is seen, as in Python
      return () => (i < v.items.length ? { done: false, value: v.items[i++] } : { done: true });
    }
    if (isObject(v) && v.kind === "range") {
      let current = v.start;
      return () => {
        const more = v.step > BigInt(0) ? current < v.stop : current > v.stop;
        if (!more) return { done: true };
        const value = current;
        current += v.step;
        return { done: false, value };
      };
    }
    if (typeof v === "string") {
      const chars = Array.from(v);
      let i = 0;
      return () => (i < chars.length ? { done: false, value: chars[i++] } : { done: true });
    }
    return this.typeError(
      `'${typeName(v)}' object is not iterable`,
      "A for loop needs a list, a range or a string to go through.",
    );
  }

  private toArray(v: Value): Value[] {
    const next = this.iterator(v);
    const items: Value[] = [];
    for (let item = next(); !item.done; item = next()) {
      items.push(item.value);
      this.checkSize(items.length);
    }
    return items;
  }

  // ---- names --------------------------------------------------------------------------------

  private lookup(name: string): Value {
    const frame = this.frame;
    if (frame.localNames?.has(name)) {
      const value = frame.vars.get(name);
      if (value !== undefined) return value;
      return this.fail(
        "UnboundLocalError",
        `cannot access local variable '${name}' where it is not associated with a value`,
        `\`${name}\` is assigned somewhere inside this function, so Python treats it as local, and it has no value yet at this line.`,
      );
    }
    const local = frame.isModule ? undefined : frame.vars.get(name);
    if (local !== undefined) return local;
    const global = this.frames[0].vars.get(name);
    if (global !== undefined) return global;
    if (BUILTINS.has(name)) return { kind: "builtin", name };
    if (UNSUPPORTED_BUILTINS.has(name)) {
      throw new UnsupportedError(`the built-in \`${name}()\``, this.line);
    }
    return this.fail(
      "NameError",
      `name '${name}' is not defined`,
      `Python doesn't know the name \`${name}\` at this line. Check the spelling, and that it was set on an earlier line.`,
    );
  }

  // ---- expressions --------------------------------------------------------------------------

  eval(e: Expr): Value {
    switch (e.k) {
      case "num":
      case "str":
      case "const":
        return e.v;
      case "name":
        return this.lookup(e.id);
      case "list":
        return this.newList(e.items.map((item) => this.eval(item)));
      case "unary":
        return this.unary(e);
      case "bin":
        return this.binary(e.op, this.eval(e.l), this.eval(e.r));
      case "logic": {
        const left = this.eval(e.l);
        if (e.op === "and") return truthy(left) ? this.eval(e.r) : left;
        return truthy(left) ? left : this.eval(e.r);
      }
      case "cmp": {
        let left = this.eval(e.first);
        for (const part of e.rest) {
          const right = this.eval(part.e);
          if (!this.compare(part.op, left, right)) return false;
          left = right;
        }
        return true;
      }
      case "call":
        return this.call(e);
      case "method":
        return this.method(e);
      case "index":
        return this.index(this.eval(e.obj), this.eval(e.idx));
    }
  }

  private unary(e: Extract<Expr, { k: "unary" }>): Value {
    const operand = this.eval(e.e);
    if (e.op === "not") return !truthy(operand);
    if (!isNumeric(operand)) {
      return this.typeError(`bad operand type for unary ${e.op}: '${typeName(operand)}'`);
    }
    const n = toNum(operand);
    if (e.op === "+") return n;
    return -n;
  }

  private compare(op: string, a: Value, b: Value): boolean {
    switch (op) {
      case "==":
        return equals(a, b);
      case "!=":
        return !equals(a, b);
      case "is":
        return a === b;
      case "is not":
        return a !== b;
      case "in":
        return this.contains(b, a);
      case "not in":
        return !this.contains(b, a);
      default:
        return this.order(op, a, b);
    }
  }

  private contains(container: Value, item: Value): boolean {
    if (typeof container === "string") {
      if (typeof item !== "string") {
        return this.typeError(
          `'in <string>' requires string as left operand, not ${typeName(item)}`,
        );
      }
      return container.includes(item);
    }
    if (isObject(container) && container.kind === "list") {
      return container.items.some((x) => equals(x, item));
    }
    if (isObject(container) && container.kind === "range") {
      return this.toArray(container).some((x) => equals(x, item));
    }
    return this.typeError(`argument of type '${typeName(container)}' is not iterable`);
  }

  private order(op: string, a: Value, b: Value): boolean {
    let cmp: number;
    if (isNumeric(a) && isNumeric(b)) {
      const x = toNum(a);
      const y = toNum(b);
      if (typeof x === "bigint" && typeof y === "bigint") cmp = x < y ? -1 : x > y ? 1 : 0;
      else {
        const p = Number(x);
        const q = Number(y);
        if (Number.isNaN(p) || Number.isNaN(q)) return false;
        cmp = p < q ? -1 : p > q ? 1 : 0;
      }
    } else if (typeof a === "string" && typeof b === "string") {
      cmp = a < b ? -1 : a > b ? 1 : 0;
    } else if (isObject(a) && a.kind === "list" && isObject(b) && b.kind === "list") {
      throw new UnsupportedError("comparing two lists with < or >", this.line);
    } else {
      return this.typeError(
        `'${op}' not supported between instances of '${typeName(a)}' and '${typeName(b)}'`,
        "These two values can't be ordered against each other. Check that both are numbers, or both are text.",
      );
    }
    switch (op) {
      case "<":
        return cmp < 0;
      case "<=":
        return cmp <= 0;
      case ">":
        return cmp > 0;
      default:
        return cmp >= 0;
    }
  }

  binary(op: "+" | "-" | "*" | "/" | "//" | "%" | "**", a: Value, b: Value): Value {
    if (op === "+") {
      if (typeof a === "string" && typeof b === "string") {
        this.checkSize(a.length + b.length);
        return a + b;
      }
      if (isObject(a) && a.kind === "list" && isObject(b) && b.kind === "list") {
        this.checkSize(a.items.length + b.items.length);
        return this.newList([...a.items, ...b.items]);
      }
      if (typeof a === "string") {
        return this.typeError(
          `can only concatenate str (not "${typeName(b)}") to str`,
          typeName(b) === "int" || typeName(b) === "float"
            ? "You can't add text and a number directly. Turn the number into text with str(...) first."
            : undefined,
        );
      }
      if (isObject(a) && a.kind === "list") {
        return this.typeError(`can only concatenate list (not "${typeName(b)}") to list`);
      }
    }
    if (op === "*") {
      const repeated = this.repeat(a, b);
      if (repeated !== undefined) return repeated;
    }
    if (isNumeric(a) && isNumeric(b)) return this.numeric(op, toNum(a), toNum(b));
    return this.typeError(
      `unsupported operand type(s) for ${op}: '${typeName(a)}' and '${typeName(b)}'`,
      a === null || b === null
        ? "One of these values is None. A function without `return` gives back None."
        : undefined,
    );
  }

  /** `"ab" * 3`, `3 * [0]`; undefined when neither side is a sequence. */
  private repeat(a: Value, b: Value): Value | undefined {
    const isSeq = (v: Value) => typeof v === "string" || (isObject(v) && v.kind === "list");
    if (!isSeq(a) && !isSeq(b)) return undefined;
    const [seq, count] = isSeq(a) ? [a, b] : [b, a];
    if (typeof count !== "bigint" && typeof count !== "boolean") {
      return this.typeError(`can't multiply sequence by non-int of type '${typeName(count)}'`);
    }
    const times = Number(toNum(count));
    const n = times < 0 ? 0 : times;
    if (typeof seq === "string") {
      this.checkSize(seq.length * n);
      return seq.repeat(n);
    }
    const list = seq as PyList;
    this.checkSize(list.items.length * n);
    const items: Value[] = [];
    for (let i = 0; i < n; i++) items.push(...list.items);
    return this.newList(items);
  }

  private numeric(
    op: "+" | "-" | "*" | "/" | "//" | "%" | "**",
    x: bigint | number,
    y: bigint | number,
  ): Value {
    if (typeof x === "bigint" && typeof y === "bigint") {
      switch (op) {
        case "+":
          return x + y;
        case "-":
          return x - y;
        case "*":
          return x * y;
        case "/":
          if (y === BigInt(0)) return this.zeroDivision("division by zero");
          return Number(x) / Number(y);
        case "//": {
          if (y === BigInt(0)) return this.zeroDivision("integer division or modulo by zero");
          let q = x / y;
          if (x % y !== BigInt(0) && x < BigInt(0) !== y < BigInt(0)) q -= BigInt(1);
          return q;
        }
        case "%": {
          if (y === BigInt(0)) return this.zeroDivision("integer modulo by zero");
          let r = x % y;
          if (r !== BigInt(0) && r < BigInt(0) !== y < BigInt(0)) r += y;
          return r;
        }
        case "**":
          if (y < BigInt(0)) {
            if (x === BigInt(0)) {
              return this.zeroDivision("0.0 cannot be raised to a negative power");
            }
            return Number(x) ** Number(y);
          }
          if (y > BigInt(2000) && x !== BigInt(0) && x !== BigInt(1) && x !== -BigInt(1)) {
            throw new UnsupportedError("very large powers", this.line);
          }
          return x ** y;
      }
    }
    const p = Number(x);
    const q = Number(y);
    switch (op) {
      case "+":
        return p + q;
      case "-":
        return p - q;
      case "*":
        return p * q;
      case "/":
        if (q === 0) return this.zeroDivision("float division by zero");
        return p / q;
      case "//":
        if (q === 0) return this.zeroDivision("float floor division by zero");
        return Math.floor(p / q);
      case "%": {
        if (q === 0) return this.zeroDivision("float modulo");
        let r = p % q;
        if (r !== 0 && r < 0 !== q < 0) r += q;
        return r;
      }
      case "**":
        if (p === 0 && q < 0) {
          return this.zeroDivision("0.0 cannot be raised to a negative power");
        }
        return p ** q;
    }
  }

  private zeroDivision(message: string): never {
    return this.fail(
      "ZeroDivisionError",
      message,
      "You divided by zero. Check what the divisor is at this line.",
    );
  }

  /** Turns an index into a valid list position, or raises the IndexError Python would. */
  private listPosition(
    length: number,
    idx: Value,
    message: string,
    verb: "read" | "assign",
  ): number {
    if (typeof idx !== "bigint" && typeof idx !== "boolean") {
      return this.typeError(
        `list indices must be integers or slices, not ${typeName(idx)}`,
        "A list position must be a whole number such as 0 or -1.",
      );
    }
    const raw = Number(toNum(idx));
    const position = raw < 0 ? raw + length : raw;
    if (position < 0 || position >= length) {
      const range =
        length === 0
          ? "The list is empty, so it has no positions yet."
          : `The list has ${plural(length, "item", "items")}, so valid positions are 0 to ${length - 1} (or -1 to -${length}).`;
      return this.fail(
        "IndexError",
        message,
        verb === "assign"
          ? `${range} You can only assign to a position that already exists; ${raw} does not.`
          : `${range} ${raw} is outside that.`,
      );
    }
    return position;
  }

  private index(obj: Value, idx: Value): Value {
    if (isObject(obj) && obj.kind === "list") {
      const position = this.listPosition(obj.items.length, idx, "list index out of range", "read");
      return obj.items[position];
    }
    if (typeof obj === "string") {
      if (typeof idx !== "bigint" && typeof idx !== "boolean") {
        return this.typeError(`string indices must be integers, not '${typeName(idx)}'`);
      }
      const chars = Array.from(obj);
      const raw = Number(toNum(idx));
      const position = raw < 0 ? raw + chars.length : raw;
      if (position < 0 || position >= chars.length) {
        return this.fail(
          "IndexError",
          "string index out of range",
          `The string has ${plural(chars.length, "character", "characters")}, so valid positions are 0 to ${chars.length - 1}. ${raw} is outside that.`,
        );
      }
      return chars[position];
    }
    if (isObject(obj) && obj.kind === "range") {
      throw new UnsupportedError("indexing a range (turn it into a list first)", this.line);
    }
    return this.typeError(
      `'${typeName(obj)}' object is not subscriptable`,
      "Only lists and strings can be indexed with [ ].",
    );
  }

  // ---- calls --------------------------------------------------------------------------------

  private call(e: Extract<Expr, { k: "call" }>): Value {
    const callee = this.eval(e.fn);
    const args = e.args.map((arg) => this.eval(arg));
    if (isObject(callee) && callee.kind === "function") return this.callFunction(callee, args);
    if (isObject(callee) && callee.kind === "builtin") return this.callBuiltin(callee.name, args);
    return this.typeError(
      `'${typeName(callee)}' object is not callable`,
      "Only functions can be called with ( ). Check that this name holds a function.",
    );
  }

  private callFunction(fn: PyFunction, args: Value[]): Value {
    const expected = fn.params.length;
    if (args.length !== expected) {
      const message =
        args.length < expected
          ? `${fn.name}() missing ${plural(expected - args.length, "required positional argument", "required positional arguments")}: ${fn.params
              .slice(args.length)
              .map((p) => `'${p}'`)
              .join(" and ")}`
          : `${fn.name}() takes ${expected} positional ${expected === 1 ? "argument" : "arguments"} but ${args.length} ${args.length === 1 ? "was" : "were"} given`;
      return this.typeError(
        message,
        `\`${fn.name}\` needs ${plural(expected, "value", "values")} in the parentheses, and this call gives ${args.length}.`,
      );
    }
    if (this.frames.length - 1 >= this.limits.maxDepth) {
      return this.fail(
        "RecursionError",
        "maximum recursion depth exceeded",
        `The function called itself more than ${this.limits.maxDepth} levels deep. A recursive function needs a base case that stops the calls.`,
      );
    }
    const label = `${fn.name}(${args.map((a) => shorten(repr(a), 14)).join(", ")})`;
    const vars = new Map<string, Value>();
    fn.params.forEach((param, i) => {
      vars.set(param, args[i]);
    });
    this.frames.push({ label, isModule: false, vars, localNames: fn.localNames });
    this.pendingEntered = label;
    let result: Value = null;
    try {
      const signal = this.execBlock(fn.body);
      if (signal?.t === "return") result = signal.value;
      else this.note(`\`${label}\` ended without \`return\`, so it gives back None.`);
    } finally {
      this.frames.pop();
    }
    return result;
  }

  private expectArgs(name: string, args: Value[], min: number, max: number): void {
    if (args.length >= min && args.length <= max) return;
    const message =
      min === max
        ? `${name}() takes ${min === 1 ? "exactly one argument" : `exactly ${min} arguments`} (${args.length} given)`
        : args.length < min
          ? `${name} expected at least ${min} argument, got ${args.length}`
          : `${name} expected at most ${max} arguments, got ${args.length}`;
    this.typeError(message, `\`${name}\` got the wrong number of values in the parentheses.`);
  }

  private callBuiltin(name: string, args: Value[]): Value {
    switch (name) {
      case "print": {
        const text = args.map(str).join(" ");
        this.output += `${text}\n`;
        this.note(`Printed: ${shorten(text) || "an empty line"}`);
        return null;
      }
      case "len": {
        this.expectArgs(name, args, 1, 1);
        const v = args[0];
        if (typeof v === "string") return BigInt(Array.from(v).length);
        if (isObject(v) && v.kind === "list") return BigInt(v.items.length);
        if (isObject(v) && v.kind === "range") return BigInt(rangeLength(v));
        return this.typeError(
          `object of type '${typeName(v)}' has no len()`,
          "len() works on lists and strings.",
        );
      }
      case "range":
        return this.makeRange(args);
      case "str":
        this.expectArgs(name, args, 0, 1);
        return args.length === 0 ? "" : str(args[0]);
      case "bool":
        this.expectArgs(name, args, 0, 1);
        return args.length === 0 ? false : truthy(args[0]);
      case "int":
        this.expectArgs(name, args, 0, 1);
        return args.length === 0 ? BigInt(0) : this.toInt(args[0]);
      case "float":
        this.expectArgs(name, args, 0, 1);
        return args.length === 0 ? 0 : this.toFloat(args[0]);
      case "abs": {
        this.expectArgs(name, args, 1, 1);
        const v = args[0];
        if (!isNumeric(v)) return this.typeError(`bad operand type for abs(): '${typeName(v)}'`);
        const n = toNum(v);
        return typeof n === "bigint" ? (n < BigInt(0) ? -n : n) : Math.abs(n);
      }
      case "sum": {
        this.expectArgs(name, args, 1, 1);
        let total: Value = BigInt(0);
        for (const item of this.toArray(args[0])) total = this.binary("+", total, item);
        return total;
      }
      case "min":
      case "max": {
        this.expectArgs(name, args, 1, Number.POSITIVE_INFINITY);
        const items = args.length === 1 ? this.toArray(args[0]) : args;
        if (items.length === 0) {
          return this.fail(
            "ValueError",
            `${name}() iterable argument is empty`,
            `\`${name}\` needs at least one value to choose from.`,
          );
        }
        let best = items[0];
        for (const item of items.slice(1)) {
          if (this.order(name === "min" ? "<" : ">", item, best)) best = item;
        }
        return best;
      }
      case "list":
        this.expectArgs(name, args, 0, 1);
        return this.newList(args.length === 0 ? [] : this.toArray(args[0]));
      default:
        throw new UnsupportedError(`the built-in \`${name}()\``, this.line);
    }
  }

  private makeRange(args: Value[]): PyRange {
    this.expectArgs("range", args, 1, 3);
    const ints = args.map((arg) => {
      if (typeof arg !== "bigint" && typeof arg !== "boolean") {
        return this.typeError(
          `'${typeName(arg)}' object cannot be interpreted as an integer`,
          "range() needs whole numbers.",
        );
      }
      return toNum(arg) as bigint;
    });
    const [start, stop, step] =
      ints.length === 1
        ? [BigInt(0), ints[0], BigInt(1)]
        : [ints[0], ints[1], ints[2] ?? BigInt(1)];
    if (step === BigInt(0)) {
      return this.fail(
        "ValueError",
        "range() arg 3 must not be zero",
        "The step of a range can't be 0.",
      );
    }
    return { kind: "range", start, stop, step };
  }

  private toInt(v: Value): bigint {
    if (typeof v === "bigint") return v;
    if (typeof v === "boolean") return v ? BigInt(1) : BigInt(0);
    if (typeof v === "number") {
      if (!Number.isFinite(v)) {
        return this.fail(
          "OverflowError",
          "cannot convert float infinity to integer",
          "That number is too large to turn into an int.",
        );
      }
      return BigInt(Math.trunc(v));
    }
    if (typeof v === "string") {
      if (/^\s*[+-]?\d+\s*$/.test(v)) return BigInt(v.trim());
      return this.fail(
        "ValueError",
        `invalid literal for int() with base 10: ${repr(v)}`,
        "That text isn't a whole number, so int() can't convert it.",
      );
    }
    return this.typeError(
      `int() argument must be a string, a bytes-like object or a real number, not '${typeName(v)}'`,
    );
  }

  private toFloat(v: Value): number {
    if (typeof v === "number") return v;
    if (typeof v === "bigint") return Number(v);
    if (typeof v === "boolean") return v ? 1 : 0;
    if (typeof v === "string") {
      if (/^\s*[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?\s*$/.test(v)) return Number(v.trim());
      return this.fail(
        "ValueError",
        `could not convert string to float: ${repr(v)}`,
        "That text isn't a number, so float() can't convert it.",
      );
    }
    return this.typeError(
      `float() argument must be a string or a real number, not '${typeName(v)}'`,
    );
  }

  // ---- methods ------------------------------------------------------------------------------

  private method(e: Extract<Expr, { k: "method" }>): Value {
    const obj = this.eval(e.obj);
    const args = e.args.map((arg) => this.eval(arg));
    const name = e.name;

    if (isObject(obj) && obj.kind === "list") {
      if (!LIST_METHODS.has(name)) {
        if (UNSUPPORTED_LIST_METHODS.has(name)) {
          throw new UnsupportedError(`the list method \`.${name}()\``, this.line);
        }
        return this.noAttribute("list", name);
      }
      return this.listMethod(obj, name, args, e.objText);
    }
    if (typeof obj === "string" && STR_METHODS.has(name)) {
      throw new UnsupportedError(`the string method \`.${name}()\``, this.line);
    }
    return this.noAttribute(typeName(obj), name);
  }

  private noAttribute(type: string, name: string): never {
    return this.fail(
      "AttributeError",
      `'${type}' object has no attribute '${name}'`,
      type === "NoneType"
        ? `This value is None, so it has no \`.${name}\`. A function without \`return\` gives back None.`
        : `A ${type} has no method called \`.${name}\`. Check the spelling and the type of this value.`,
    );
  }

  private listMethod(list: PyList, name: string, args: Value[], objText: string): Value {
    const changed = () =>
      this.note(`\`${objText}\` is list #${list.id}, now ${shorten(repr(list), 60)}.`);
    switch (name) {
      case "append": {
        this.expectArgs("list.append", args, 1, 1);
        this.checkSize(list.items.length + 1);
        list.items.push(args[0]);
        changed();
        return null;
      }
      case "extend": {
        this.expectArgs("list.extend", args, 1, 1);
        const items = this.toArray(args[0]);
        this.checkSize(list.items.length + items.length);
        list.items.push(...items);
        changed();
        return null;
      }
      case "insert": {
        this.expectArgs("list.insert", args, 2, 2);
        const at = args[0];
        if (typeof at !== "bigint" && typeof at !== "boolean") {
          return this.typeError(`'${typeName(at)}' object cannot be interpreted as an integer`);
        }
        const raw = Number(toNum(at));
        const position = Math.min(
          Math.max(raw < 0 ? raw + list.items.length : raw, 0),
          list.items.length,
        );
        this.checkSize(list.items.length + 1);
        list.items.splice(position, 0, args[1]);
        changed();
        return null;
      }
      case "pop": {
        this.expectArgs("list.pop", args, 0, 1);
        if (list.items.length === 0) {
          return this.fail(
            "IndexError",
            "pop from empty list",
            "You can't pop from an empty list: there is nothing to remove.",
          );
        }
        let position = list.items.length - 1;
        if (args.length === 1) {
          const at = args[0];
          if (typeof at !== "bigint" && typeof at !== "boolean") {
            return this.typeError(`'${typeName(at)}' object cannot be interpreted as an integer`);
          }
          const raw = Number(toNum(at));
          position = raw < 0 ? raw + list.items.length : raw;
          if (position < 0 || position >= list.items.length) {
            return this.fail(
              "IndexError",
              "pop index out of range",
              `The list has ${plural(list.items.length, "item", "items")}, so ${raw} is not a position you can pop.`,
            );
          }
        }
        const [removed] = list.items.splice(position, 1);
        changed();
        return removed;
      }
      default: {
        // copy
        this.expectArgs("list.copy", args, 0, 0);
        return this.newList([...list.items]);
      }
    }
  }
}

// ---- public entry point ---------------------------------------------------------------------

/** Shown if the interpreter itself hits a bug; the fuzz test asserts no snippet ever gets this. */
export const INTERNAL_MESSAGE = "This mini-runner hit something it can't handle.";

function limitMessage(limits: RunLimits): string {
  return `Stopped after ${limits.maxSteps} steps. This loop may never end.`;
}

export function runProgram(source: string, limits: RunLimits = DEFAULT_LIMITS): RunResult {
  const empty = (
    status: RunResult["status"],
    message: string | null,
    error: RunError | null,
  ): RunResult => ({
    status,
    steps: [],
    output: "",
    message,
    error,
  });

  if (source.length > MAX_SOURCE_CHARS) {
    return empty(
      "unsupported",
      "This mini-runner doesn't support programs longer than 5,000 characters yet.",
      null,
    );
  }

  let program: Stmt[];
  try {
    program = parseProgram(source);
  } catch (caught) {
    if (caught instanceof UnsupportedError) {
      return empty("unsupported", `This mini-runner doesn't support ${caught.feature} yet.`, null);
    }
    if (caught instanceof SyntaxIssue) {
      return empty("syntax", null, {
        name: caught.errorName,
        message: caught.message,
        line: caught.line,
        plain:
          caught.errorName === "IndentationError"
            ? "The spaces at the start of a line don't match the block around it."
            : "Python can't read this line. Check for a missing colon, bracket, quote or operator.",
      });
    }
    return empty("syntax", null, {
      name: "SyntaxError",
      message: "too complex to read",
      line: 1,
      plain: "This code is too deeply nested for the mini-runner to read.",
    });
  }

  const machine = new Machine(limits);
  const finish = (
    status: RunResult["status"],
    last: Step,
    message: string | null,
    error: RunError | null,
  ): RunResult => {
    machine.steps.push(last);
    return { status, steps: machine.steps, output: machine.output, message, error };
  };

  try {
    machine.execBlock(program);
    return finish("ok", machine.terminal("end", null), null, null);
  } catch (caught) {
    if (caught instanceof PyError) {
      const error: RunError = {
        name: caught.errorName,
        message: caught.message,
        plain: caught.plain,
        line: caught.line,
      };
      const last: Step = {
        kind: "error",
        line: caught.line,
        frames: caught.frames,
        output: caught.output,
        after: [],
        message: `${error.name}: ${error.message}`,
      };
      return finish("error", last, null, error);
    }
    if (caught instanceof StepLimitReached) {
      const message = limitMessage(limits);
      return finish("limit", machine.terminal("limit", caught.line, message), message, null);
    }
    if (caught instanceof UnsupportedError) {
      const message = `This mini-runner doesn't support ${caught.feature} yet.`;
      return finish(
        "unsupported",
        machine.terminal("unsupported", caught.line, message),
        message,
        null,
      );
    }
    if (caught instanceof RangeError) {
      const message = "This code nests too deeply for the mini-runner.";
      return finish("unsupported", machine.terminal("unsupported", null, message), message, null);
    }
    const message = INTERNAL_MESSAGE;
    return finish("unsupported", machine.terminal("unsupported", null, message), message, null);
  }
}
