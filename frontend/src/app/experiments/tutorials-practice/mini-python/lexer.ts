/**
 * Lexer for the teaching subset: NAME / NUMBER / STRING / OP tokens plus NEWLINE, INDENT and DEDENT
 * so the parser never counts spaces. Syntax Python has but this runner does not (f-strings, dicts,
 * `;`, decorators, bit operators ...) raises `UnsupportedError` with a plain name for it.
 */

import { SyntaxIssue, UnsupportedError } from "./errors";
import type { Token } from "./types";

export function normalizeSource(source: string): string {
  return source.replace(/\r\n?/g, "\n");
}

const NAME_START = /[A-Za-z_]/;
const NAME_PART = /[A-Za-z0-9_]/;
const DIGIT = /[0-9]/;

const THREE_CHAR_OPS = new Set(["//=", "**="]);
const TWO_CHAR_OPS = new Set(["==", "!=", "<=", ">=", "//", "**", "+=", "-=", "*=", "/=", "%="]);
const ONE_CHAR_OPS = new Set([
  "+",
  "-",
  "*",
  "/",
  "%",
  "<",
  ">",
  "=",
  "(",
  ")",
  "[",
  "]",
  ",",
  ":",
  ".",
]);

/** Operators and punctuation Python has that we do not, with the words used in the message. */
const UNSUPPORTED_PUNCT: Record<string, string> = {
  "{": "dictionaries and sets ({ })",
  "}": "dictionaries and sets ({ })",
  ";": "several statements on one line (;)",
  "@": "decorators and the @ operator",
  "&": "bitwise operators",
  "|": "bitwise operators",
  "^": "bitwise operators",
  "~": "bitwise operators",
  "<<": "bitwise operators",
  ">>": "bitwise operators",
  "->": "type annotations",
  ":=": "the := operator",
  "\\": "a backslash line continuation",
};

const ESCAPES: Record<string, string> = {
  n: "\n",
  t: "\t",
  r: "\r",
  "\\": "\\",
  "'": "'",
  '"': '"',
  "0": "\0",
};

export function tokenize(rawSource: string): Token[] {
  const src = normalizeSource(rawSource);
  const tokens: Token[] = [];
  const indents = [0];
  const brackets: { char: string; line: number }[] = [];
  let pos = 0;
  let line = 1;
  let atLineStart = true;
  let lineHasTokens = false;

  const push = (type: Token["type"], text: string, start: number, end: number, at = line) => {
    tokens.push({ type, text, line: at, start, end });
  };

  while (pos < src.length) {
    if (atLineStart && brackets.length === 0) {
      // Measure indentation; skip blank and comment-only lines entirely.
      let width = 0;
      let cursor = pos;
      while (cursor < src.length && (src[cursor] === " " || src[cursor] === "\t")) {
        width = src[cursor] === "\t" ? (Math.floor(width / 8) + 1) * 8 : width + 1;
        cursor++;
      }
      if (cursor >= src.length) {
        pos = cursor;
        break;
      }
      if (src[cursor] === "\n") {
        pos = cursor + 1;
        line++;
        continue;
      }
      if (src[cursor] === "#") {
        while (cursor < src.length && src[cursor] !== "\n") cursor++;
        pos = cursor + 1;
        line++;
        continue;
      }
      pos = cursor;
      const top = indents[indents.length - 1];
      if (width > top) {
        indents.push(width);
        push("INDENT", "", pos, pos);
      } else if (width < top) {
        while (width < indents[indents.length - 1]) {
          indents.pop();
          push("DEDENT", "", pos, pos);
        }
        if (width !== indents[indents.length - 1]) {
          throw new SyntaxIssue(
            "IndentationError",
            "unindent does not match any outer indentation level",
            line,
          );
        }
      }
      atLineStart = false;
    }

    const ch = src[pos];

    if (ch === "\n") {
      if (brackets.length === 0) {
        if (lineHasTokens) push("NEWLINE", "", pos, pos + 1);
        lineHasTokens = false;
        atLineStart = true;
      }
      pos++;
      line++;
      continue;
    }
    if (ch === " " || ch === "\t") {
      pos++;
      continue;
    }
    if (ch === "#") {
      while (pos < src.length && src[pos] !== "\n") pos++;
      continue;
    }

    lineHasTokens = true;

    if (NAME_START.test(ch)) {
      let end = pos + 1;
      while (end < src.length && NAME_PART.test(src[end])) end++;
      const word = src.slice(pos, end);
      const next = src[end];
      if ((next === '"' || next === "'") && /^[fFrRbBuU]{1,2}$/.test(word)) {
        throw new UnsupportedError(
          /[fF]/.test(word) ? "f-strings" : 'string prefixes like r"" or b""',
          line,
        );
      }
      push("NAME", word, pos, end);
      pos = end;
      continue;
    }

    if (DIGIT.test(ch) || (ch === "." && DIGIT.test(src[pos + 1] ?? ""))) {
      pos = readNumber(src, pos, line, push);
      continue;
    }

    if (ch === '"' || ch === "'") {
      pos = readString(src, pos, line, push);
      continue;
    }

    const three = src.slice(pos, pos + 3);
    const two = src.slice(pos, pos + 2);
    if (THREE_CHAR_OPS.has(three)) {
      push("OP", three, pos, pos + 3);
      pos += 3;
      continue;
    }
    if (UNSUPPORTED_PUNCT[two]) throw new UnsupportedError(UNSUPPORTED_PUNCT[two], line);
    if (TWO_CHAR_OPS.has(two)) {
      push("OP", two, pos, pos + 2);
      pos += 2;
      continue;
    }
    if (UNSUPPORTED_PUNCT[ch]) throw new UnsupportedError(UNSUPPORTED_PUNCT[ch], line);
    if (ONE_CHAR_OPS.has(ch)) {
      if (ch === "(" || ch === "[") brackets.push({ char: ch, line });
      if (ch === ")" || ch === "]") {
        const open = brackets.pop();
        const expected = ch === ")" ? "(" : "[";
        if (!open || open.char !== expected) {
          throw new SyntaxIssue("SyntaxError", `unmatched '${ch}'`, line);
        }
      }
      push("OP", ch, pos, pos + 1);
      pos++;
      continue;
    }
    throw new SyntaxIssue("SyntaxError", `invalid character '${ch}'`, line);
  }

  const unclosed = brackets[brackets.length - 1];
  if (unclosed) {
    throw new SyntaxIssue("SyntaxError", `'${unclosed.char}' was never closed`, unclosed.line);
  }
  if (lineHasTokens) push("NEWLINE", "", src.length, src.length);
  while (indents.length > 1) {
    indents.pop();
    push("DEDENT", "", src.length, src.length);
  }
  push("EOF", "", src.length, src.length);
  return tokens;
}

type Push = (type: Token["type"], text: string, start: number, end: number, at?: number) => void;

function readNumber(src: string, start: number, line: number, push: Push): number {
  let pos = start;
  if (src[pos] === "0" && /[xXoObB]/.test(src[pos + 1] ?? "")) {
    throw new UnsupportedError("hex, octal and binary numbers", line);
  }
  while (DIGIT.test(src[pos] ?? "")) pos++;
  let isFloat = false;
  if (src[pos] === ".") {
    isFloat = true;
    pos++;
    while (DIGIT.test(src[pos] ?? "")) pos++;
  }
  if (/[eE]/.test(src[pos] ?? "") && /[0-9+-]/.test(src[pos + 1] ?? "")) {
    const save = pos;
    pos++;
    if (src[pos] === "+" || src[pos] === "-") pos++;
    if (DIGIT.test(src[pos] ?? "")) {
      isFloat = true;
      while (DIGIT.test(src[pos] ?? "")) pos++;
    } else {
      pos = save;
    }
  }
  const next = src[pos] ?? "";
  if (next === "_") throw new UnsupportedError("underscores inside numbers", line);
  if (next === "j" || next === "J") throw new UnsupportedError("complex numbers", line);
  if (NAME_PART.test(next)) {
    throw new SyntaxIssue("SyntaxError", "invalid decimal literal", line);
  }
  const text = src.slice(start, pos);
  // Python 3 forbids `007`; keep the rule for plain integers.
  if (!isFloat && text.length > 1 && text.startsWith("0") && /[1-9]/.test(text)) {
    throw new SyntaxIssue(
      "SyntaxError",
      "leading zeros in decimal integer literals are not permitted",
      line,
    );
  }
  push("NUMBER", text, start, pos);
  return pos;
}

function readString(src: string, start: number, line: number, push: Push): number {
  const quote = src[start];
  if (src.slice(start, start + 3) === quote.repeat(3)) {
    throw new UnsupportedError("triple-quoted strings", line);
  }
  let pos = start + 1;
  let value = "";
  while (pos < src.length && src[pos] !== quote) {
    const ch = src[pos];
    if (ch === "\n") break;
    if (ch === "\\") {
      const next = src[pos + 1];
      if (next === undefined || next === "\n") {
        throw new UnsupportedError("a backslash line continuation", line);
      }
      value += ESCAPES[next] ?? `\\${next}`;
      pos += 2;
      continue;
    }
    value += ch;
    pos++;
  }
  if (src[pos] !== quote) {
    throw new SyntaxIssue(
      "SyntaxError",
      `unterminated string literal (detected at line ${line})`,
      line,
    );
  }
  push("STRING", value, start, pos + 1);
  return pos + 1;
}
