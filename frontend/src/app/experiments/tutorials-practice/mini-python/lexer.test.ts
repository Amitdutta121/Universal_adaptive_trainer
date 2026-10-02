import { describe, expect, it } from "vitest";
import { SyntaxIssue, UnsupportedError } from "./errors";
import { tokenize } from "./lexer";

const kinds = (src: string) => tokenize(src).map((t) => t.type);

describe("lexer", () => {
  it("emits INDENT / DEDENT / NEWLINE and skips blank and comment-only lines", () => {
    const src = "if x:\n\n    # note\n    y = 1\nz = 2\n";
    expect(kinds(src)).toEqual([
      "NAME",
      "NAME",
      "OP",
      "NEWLINE",
      "INDENT",
      "NAME",
      "OP",
      "NUMBER",
      "NEWLINE",
      "DEDENT",
      "NAME",
      "OP",
      "NUMBER",
      "NEWLINE",
      "EOF",
    ]);
  });

  it("closes open blocks at the end and needs no trailing newline", () => {
    expect(kinds("while x:\n    pass")).toEqual([
      "NAME",
      "NAME",
      "OP",
      "NEWLINE",
      "INDENT",
      "NAME",
      "NEWLINE",
      "DEDENT",
      "EOF",
    ]);
  });

  it("joins lines inside brackets", () => {
    const tokens = tokenize("a = [1,\n     2]\nb = 3\n");
    expect(tokens.filter((t) => t.type === "NEWLINE")).toHaveLength(2);
    expect(tokens.find((t) => t.text === "b")?.line).toBe(3);
  });

  it("reads numbers, escapes in strings and multi-character operators", () => {
    const tokens = tokenize('x //= 1.5e3 + .5\ns = "a\\tb\\"c"\n');
    expect(tokens.map((t) => t.text).slice(0, 5)).toEqual(["x", "//=", "1.5e3", "+", ".5"]);
    expect(tokens.find((t) => t.type === "STRING")?.text).toBe('a\tb"c');
  });

  it("names unsupported syntax instead of failing generically", () => {
    const feature = (src: string) => {
      try {
        tokenize(src);
      } catch (e) {
        return e instanceof UnsupportedError ? e.feature : `other: ${String(e)}`;
      }
      return "none";
    };
    expect(feature('print(f"{x}")')).toBe("f-strings");
    expect(feature("d = {}")).toContain("dictionaries");
    expect(feature('s = """a"""')).toBe("triple-quoted strings");
    expect(feature("x = 1; y = 2")).toContain("several statements");
    expect(feature("x = 0xFF")).toContain("hex");
    expect(feature("x = a & b")).toContain("bitwise");
    expect(feature("@decorator\ndef f(): pass")).toContain("decorators");
  });

  it("reports bad indentation, unterminated strings and unclosed brackets as syntax errors", () => {
    const issue = (src: string) => {
      try {
        tokenize(src);
      } catch (e) {
        if (e instanceof SyntaxIssue) return `${e.errorName}: ${e.message} @${e.line}`;
      }
      return "none";
    };
    expect(issue("if x:\n        a = 1\n    b = 2\n")).toBe(
      "IndentationError: unindent does not match any outer indentation level @3",
    );
    expect(issue('x = "abc\n')).toContain("unterminated string literal");
    expect(issue("x = (1, 2\n")).toBe("SyntaxError: '(' was never closed @1");
    expect(issue("x = 1)\n")).toBe("SyntaxError: unmatched ')' @1");
    expect(issue("x = 5 $ 3\n")).toContain("invalid character");
  });
});
