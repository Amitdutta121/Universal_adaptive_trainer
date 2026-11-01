/**
 * Runtime values and how Python prints them. Python's int is a JS bigint, float a JS number, so
 * `7 / 2` and `7 // 2` stay distinguishable and integers never lose precision.
 */

import type { Stmt } from "./types";

export interface PyList {
  kind: "list";
  /** Identity shown in the trace, so `b = a` is visibly the same list. */
  id: number;
  items: Value[];
}

export interface PyRange {
  kind: "range";
  start: bigint;
  stop: bigint;
  step: bigint;
}

export interface PyFunction {
  kind: "function";
  name: string;
  params: string[];
  localNames: Set<string>;
  body: Stmt[];
}

export interface PyBuiltin {
  kind: "builtin";
  name: string;
}

export type Value =
  | bigint
  | number
  | boolean
  | string
  | null
  | PyList
  | PyRange
  | PyFunction
  | PyBuiltin;

export function isObject(v: Value): v is PyList | PyRange | PyFunction | PyBuiltin {
  return typeof v === "object" && v !== null;
}

export function typeName(v: Value): string {
  switch (typeof v) {
    case "bigint":
      return "int";
    case "number":
      return "float";
    case "boolean":
      return "bool";
    case "string":
      return "str";
    default:
      if (v === null) return "NoneType";
      if (v.kind === "list") return "list";
      if (v.kind === "range") return "range";
      if (v.kind === "function") return "function";
      return "builtin_function_or_method";
  }
}

export function truthy(v: Value): boolean {
  switch (typeof v) {
    case "bigint":
      return v !== BigInt(0);
    case "number":
      return v !== 0;
    case "boolean":
      return v;
    case "string":
      return v.length > 0;
    default:
      if (v === null) return false;
      if (v.kind === "list") return v.items.length > 0;
      if (v.kind === "range") return rangeLength(v) > 0;
      return true;
  }
}

// ---- number formatting ----------------------------------------------------------------------

/** Python's `repr(float)`: shortest round-trip digits, `.0` on whole numbers, exponent from 1e16. */
export function floatRepr(n: number): string {
  if (Number.isNaN(n)) return "nan";
  if (!Number.isFinite(n)) return n < 0 ? "-inf" : "inf";
  if (n === 0) return Object.is(n, -0) ? "-0.0" : "0.0";
  const abs = Math.abs(n);
  if (abs >= 1e16 || abs < 1e-4) {
    const [mantissa, exponent] = n.toExponential().split("e");
    const sign = exponent.startsWith("-") ? "-" : "+";
    const digits = exponent.replace(/^[+-]/, "").padStart(2, "0");
    return `${mantissa}e${sign}${digits}`;
  }
  const text = String(n);
  return text.includes(".") ? text : `${text}.0`;
}

// ---- repr / str -----------------------------------------------------------------------------

export function stringRepr(s: string): string {
  const quote = s.includes("'") && !s.includes('"') ? '"' : "'";
  let body = "";
  for (const ch of s) {
    if (ch === "\\") body += "\\\\";
    else if (ch === "\n") body += "\\n";
    else if (ch === "\t") body += "\\t";
    else if (ch === "\r") body += "\\r";
    else if (ch === quote) body += `\\${ch}`;
    else body += ch;
  }
  return quote + body + quote;
}

export function rangeLength(r: PyRange): number {
  if (r.step > BigInt(0))
    return r.start >= r.stop ? 0 : Number((r.stop - r.start + r.step - BigInt(1)) / r.step);
  return r.start <= r.stop ? 0 : Number((r.start - r.stop - r.step - BigInt(1)) / -r.step);
}

export function repr(v: Value, seen: PyList[] = []): string {
  switch (typeof v) {
    case "bigint":
      return v.toString();
    case "number":
      return floatRepr(v);
    case "boolean":
      return v ? "True" : "False";
    case "string":
      return stringRepr(v);
    default:
      if (v === null) return "None";
      if (v.kind === "list") {
        if (seen.includes(v)) return "[...]";
        return `[${v.items.map((item) => repr(item, [...seen, v])).join(", ")}]`;
      }
      if (v.kind === "range") {
        return v.step === BigInt(1)
          ? `range(${v.start}, ${v.stop})`
          : `range(${v.start}, ${v.stop}, ${v.step})`;
      }
      if (v.kind === "function") return `<function ${v.name}>`;
      return `<built-in function ${v.name}>`;
  }
}

export function str(v: Value): string {
  return typeof v === "string" ? v : repr(v);
}

// ---- equality -------------------------------------------------------------------------------

export function isNumeric(v: Value): v is bigint | number | boolean {
  return typeof v === "bigint" || typeof v === "number" || typeof v === "boolean";
}

/** bool counts as int in arithmetic and comparison. */
export function toNum(v: bigint | number | boolean): bigint | number {
  return typeof v === "boolean" ? (v ? BigInt(1) : BigInt(0)) : v;
}

export function equals(a: Value, b: Value): boolean {
  if (isNumeric(a) && isNumeric(b)) {
    const x = toNum(a);
    const y = toNum(b);
    if (typeof x === "bigint" && typeof y === "bigint") return x === y;
    return Number(x) === Number(y);
  }
  if (typeof a === "string" || typeof b === "string") return a === b;
  if (a === null || b === null) return a === b;
  if (isObject(a) && isObject(b)) {
    if (a.kind === "list" && b.kind === "list") {
      return (
        a.items.length === b.items.length && a.items.every((item, i) => equals(item, b.items[i]))
      );
    }
    return a === b;
  }
  return false;
}
