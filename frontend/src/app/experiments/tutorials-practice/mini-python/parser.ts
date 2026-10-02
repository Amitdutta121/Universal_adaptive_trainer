/**
 * Recursive-descent parser for the teaching subset. Produces `Stmt[]` or throws `SyntaxIssue` (not
 * valid Python) / `UnsupportedError` (valid Python we do not implement).
 *
 * Deliberate limits, each reported by name: no body on the same line as the colon, no nested
 * `def`, no tuples, no keyword or default arguments, no slicing, no comprehensions, no `x if c else y`.
 */

import { SyntaxIssue, UnsupportedError } from "./errors";
import { normalizeSource, tokenize } from "./lexer";
import type { AugOp, CompareOp, Expr, Stmt, Target, Token } from "./types";

const KEYWORDS = new Set([
  "False",
  "None",
  "True",
  "and",
  "as",
  "assert",
  "async",
  "await",
  "break",
  "class",
  "continue",
  "def",
  "del",
  "elif",
  "else",
  "except",
  "finally",
  "for",
  "from",
  "global",
  "if",
  "import",
  "in",
  "is",
  "lambda",
  "nonlocal",
  "not",
  "or",
  "pass",
  "raise",
  "return",
  "try",
  "while",
  "with",
  "yield",
]);

/** Statement-starting keywords that are real Python but outside the subset. */
const UNSUPPORTED_STATEMENTS: Record<string, string> = {
  import: "import",
  from: "import",
  class: "classes",
  try: "try / except",
  except: "try / except",
  finally: "try / except",
  with: "with blocks",
  global: "the global statement",
  nonlocal: "the nonlocal statement",
  del: "del",
  assert: "assert",
  raise: "raise",
  yield: "generators (yield)",
  async: "async code",
  await: "async code",
  lambda: "lambda",
};

const AUG_OPS: Record<string, AugOp> = {
  "+=": "+",
  "-=": "-",
  "*=": "*",
  "/=": "/",
  "//=": "//",
  "%=": "%",
};

const COMPARE_OPS = new Set(["==", "!=", "<", "<=", ">", ">="]);

export function parseProgram(rawSource: string): Stmt[] {
  const source = normalizeSource(rawSource);
  return new Parser(source, tokenize(source)).program();
}

class Parser {
  private pos = 0;
  private functionDepth = 0;
  private loopDepth = 0;
  /** Names assigned in the function being parsed (null at module level). */
  private locals: Set<string> | null = null;

  constructor(
    private readonly source: string,
    private readonly tokens: Token[],
  ) {}

  // ---- token helpers ------------------------------------------------------------------------

  private peek(offset = 0): Token {
    return this.tokens[Math.min(this.pos + offset, this.tokens.length - 1)];
  }

  private next(): Token {
    const token = this.tokens[this.pos];
    if (this.pos < this.tokens.length - 1) this.pos++;
    return token;
  }

  private isOp(text: string, offset = 0): boolean {
    const token = this.peek(offset);
    return token.type === "OP" && token.text === text;
  }

  private isName(text: string, offset = 0): boolean {
    const token = this.peek(offset);
    return token.type === "NAME" && token.text === text;
  }

  private prevEnd(): number {
    return this.tokens[Math.max(this.pos - 1, 0)].end;
  }

  private invalid(token: Token = this.peek()): never {
    if (token.type === "INDENT") {
      throw new SyntaxIssue("IndentationError", "unexpected indent", token.line);
    }
    throw new SyntaxIssue("SyntaxError", "invalid syntax", token.line);
  }

  private expectOp(text: string): Token {
    if (!this.isOp(text)) this.invalid();
    return this.next();
  }

  // ---- statements ---------------------------------------------------------------------------

  program(): Stmt[] {
    const body: Stmt[] = [];
    while (this.peek().type !== "EOF") body.push(this.statement());
    return body;
  }

  private statement(): Stmt {
    const token = this.peek();
    if (token.type === "INDENT") this.invalid(token);
    if (token.type === "NAME") {
      switch (token.text) {
        case "if":
          return this.ifStatement();
        case "while":
          return this.whileStatement();
        case "for":
          return this.forStatement();
        case "def":
          return this.defStatement();
        default: {
          const unsupported = UNSUPPORTED_STATEMENTS[token.text];
          if (unsupported) throw new UnsupportedError(unsupported, token.line);
        }
      }
    }
    const stmt = this.simpleStatement();
    if (this.peek().type !== "NEWLINE") {
      this.checkTrailing();
      this.invalid();
    }
    this.next();
    return stmt;
  }

  /** After a complete simple statement, name well-known extras instead of "invalid syntax". */
  private checkTrailing(): void {
    const token = this.peek();
    if (token.type === "NAME" && token.text === "if") {
      throw new UnsupportedError("conditional expressions (x if c else y)", token.line);
    }
    if (token.type === "NAME" && token.text === "for") {
      throw new UnsupportedError("comprehensions", token.line);
    }
    if (token.type === "OP" && token.text === ",") {
      throw new UnsupportedError("tuples and multiple assignment", token.line);
    }
  }

  private simpleStatement(): Stmt {
    const token = this.peek();
    const line = token.line;
    if (token.type === "NAME") {
      switch (token.text) {
        case "pass":
          this.next();
          return { k: "pass", line };
        case "break":
          if (this.loopDepth === 0) {
            throw new SyntaxIssue("SyntaxError", "'break' outside loop", line);
          }
          this.next();
          return { k: "break", line };
        case "continue":
          if (this.loopDepth === 0) {
            throw new SyntaxIssue("SyntaxError", "'continue' not properly in loop", line);
          }
          this.next();
          return { k: "continue", line };
        case "return": {
          if (this.functionDepth === 0) {
            throw new SyntaxIssue("SyntaxError", "'return' outside function", line);
          }
          this.next();
          const value = this.peek().type === "NEWLINE" ? null : this.expression();
          return { k: "return", value, line };
        }
        default:
      }
    }

    const startOffset = token.start;
    const first = this.expression();
    const firstText = this.source.slice(startOffset, this.prevEnd());

    if (this.isOp("=")) {
      const targets: Target[] = [this.toTarget(first, firstText, line)];
      let value: Expr = first;
      while (this.isOp("=")) {
        this.next();
        const valueStart = this.peek().start;
        value = this.expression();
        if (this.isOp("=")) {
          targets.push(this.toTarget(value, this.source.slice(valueStart, this.prevEnd()), line));
        }
      }
      for (const target of targets) this.noteAssigned(target);
      return { k: "assign", targets, value, line };
    }

    const op = this.peek();
    if (op.type === "OP" && AUG_OPS[op.text]) {
      this.next();
      const target = this.toTarget(first, firstText, line);
      this.noteAssigned(target);
      return { k: "aug", target, op: AUG_OPS[op.text], value: this.expression(), line };
    }
    return { k: "expr", e: first, line };
  }

  private toTarget(expr: Expr, text: string, line: number): Target {
    if (expr.k === "name") return { k: "name", id: expr.id, text };
    if (expr.k === "index") return { k: "index", obj: expr.obj, idx: expr.idx, text };
    if (expr.k === "method") {
      throw new SyntaxIssue("SyntaxError", "cannot assign to function call here", line);
    }
    throw new SyntaxIssue(
      "SyntaxError",
      "cannot assign to expression here. Maybe you meant '==' instead of '='?",
      line,
    );
  }

  private noteAssigned(target: Target): void {
    if (target.k === "name") this.locals?.add(target.id);
  }

  private block(header: string, headerLine: number): Stmt[] {
    this.expectOp(":");
    if (this.peek().type !== "NEWLINE") {
      throw new UnsupportedError(
        "a body on the same line as the colon (put it on its own indented line)",
        this.peek().line,
      );
    }
    this.next();
    if (this.peek().type !== "INDENT") {
      throw new SyntaxIssue(
        "IndentationError",
        `expected an indented block after ${header} on line ${headerLine}`,
        this.peek().line,
      );
    }
    this.next();
    const body: Stmt[] = [];
    while (this.peek().type !== "DEDENT" && this.peek().type !== "EOF") body.push(this.statement());
    if (this.peek().type === "DEDENT") this.next();
    return body;
  }

  private ifStatement(): Stmt {
    const keyword = this.next(); // `if` or `elif`
    const start = this.peek().start;
    const test = this.expression();
    const testText = this.source.slice(start, this.prevEnd());
    const label = keyword.text === "if" ? "'if' statement" : "'elif' statement";
    const body = this.block(label, keyword.line);
    let orelse: Stmt[] = [];
    if (this.isName("elif")) {
      orelse = [this.ifStatement()];
    } else if (this.isName("else")) {
      const elseToken = this.next();
      orelse = this.block("'else' statement", elseToken.line);
    }
    return { k: "if", test, testText, body, orelse, line: keyword.line };
  }

  private whileStatement(): Stmt {
    const keyword = this.next();
    const start = this.peek().start;
    const test = this.expression();
    const testText = this.source.slice(start, this.prevEnd());
    this.loopDepth++;
    const body = this.block("'while' statement", keyword.line);
    this.loopDepth--;
    if (this.isName("else")) throw new UnsupportedError("else after a loop", this.peek().line);
    return { k: "while", test, testText, body, line: keyword.line };
  }

  private forStatement(): Stmt {
    const keyword = this.next();
    const target = this.peek();
    if (target.type !== "NAME" || KEYWORDS.has(target.text)) this.invalid();
    this.next();
    if (this.isOp(",")) throw new UnsupportedError("tuples and multiple assignment", target.line);
    if (!this.isName("in")) this.invalid();
    this.next();
    const iter = this.expression();
    this.locals?.add(target.text);
    this.loopDepth++;
    const body = this.block("'for' statement", keyword.line);
    this.loopDepth--;
    if (this.isName("else")) throw new UnsupportedError("else after a loop", this.peek().line);
    return { k: "for", varName: target.text, iter, body, line: keyword.line };
  }

  private defStatement(): Stmt {
    const keyword = this.next();
    if (this.functionDepth > 0) {
      throw new UnsupportedError("a function defined inside another function", keyword.line);
    }
    const nameToken = this.peek();
    if (nameToken.type !== "NAME" || KEYWORDS.has(nameToken.text)) this.invalid();
    this.next();
    this.expectOp("(");
    const params: string[] = [];
    while (!this.isOp(")")) {
      const param = this.peek();
      if (this.isOp("*") || this.isOp("**")) {
        throw new UnsupportedError("*args and **kwargs", param.line);
      }
      if (param.type !== "NAME" || KEYWORDS.has(param.text)) this.invalid();
      this.next();
      if (this.isOp("=")) throw new UnsupportedError("default parameter values", param.line);
      if (params.includes(param.text)) {
        throw new SyntaxIssue(
          "SyntaxError",
          `duplicate argument '${param.text}' in function definition`,
          param.line,
        );
      }
      params.push(param.text);
      if (this.isOp(",")) this.next();
      else if (!this.isOp(")")) this.invalid();
    }
    this.next(); // )
    if (this.isOp("->")) this.invalid();

    const outerLocals = this.locals;
    const outerLoops = this.loopDepth;
    this.locals = new Set(params);
    this.loopDepth = 0;
    this.functionDepth++;
    const body = this.block("function definition", keyword.line);
    this.functionDepth--;
    const localNames = [...this.locals];
    this.locals = outerLocals;
    this.loopDepth = outerLoops;
    return { k: "def", name: nameToken.text, params, localNames, body, line: keyword.line };
  }

  // ---- expressions --------------------------------------------------------------------------

  /** A full expression. `x if c else y` and lambdas are named as unsupported, not misparsed. */
  private expression(): Expr {
    if (this.isName("lambda")) throw new UnsupportedError("lambda", this.peek().line);
    return this.orTest();
  }

  private orTest(): Expr {
    let left = this.andTest();
    while (this.isName("or")) {
      const line = this.next().line;
      left = { k: "logic", op: "or", l: left, r: this.andTest(), line };
    }
    return left;
  }

  private andTest(): Expr {
    let left = this.notTest();
    while (this.isName("and")) {
      const line = this.next().line;
      left = { k: "logic", op: "and", l: left, r: this.notTest(), line };
    }
    return left;
  }

  private notTest(): Expr {
    if (this.isName("not")) {
      const line = this.next().line;
      return { k: "unary", op: "not", e: this.notTest(), line };
    }
    return this.comparison();
  }

  private comparison(): Expr {
    const first = this.arith();
    const rest: { op: CompareOp; e: Expr }[] = [];
    for (;;) {
      const token = this.peek();
      let op: CompareOp | null = null;
      if (token.type === "OP" && COMPARE_OPS.has(token.text)) {
        this.next();
        op = token.text as CompareOp;
      } else if (this.isName("in")) {
        this.next();
        op = "in";
      } else if (this.isName("not") && this.isName("in", 1)) {
        this.next();
        this.next();
        op = "not in";
      } else if (this.isName("is")) {
        this.next();
        if (this.isName("not")) {
          this.next();
          op = "is not";
        } else {
          op = "is";
        }
      }
      if (!op) break;
      rest.push({ op, e: this.arith() });
    }
    return rest.length === 0 ? first : { k: "cmp", first, rest, line: first.line };
  }

  private arith(): Expr {
    let left = this.term();
    while (this.isOp("+") || this.isOp("-")) {
      const op = this.next();
      left = { k: "bin", op: op.text as "+" | "-", l: left, r: this.term(), line: op.line };
    }
    return left;
  }

  private term(): Expr {
    let left = this.factor();
    while (this.isOp("*") || this.isOp("/") || this.isOp("//") || this.isOp("%")) {
      const op = this.next();
      left = {
        k: "bin",
        op: op.text as "*" | "/" | "//" | "%",
        l: left,
        r: this.factor(),
        line: op.line,
      };
    }
    return left;
  }

  private factor(): Expr {
    if (this.isOp("-") || this.isOp("+")) {
      const op = this.next();
      return { k: "unary", op: op.text as "-" | "+", e: this.factor(), line: op.line };
    }
    return this.power();
  }

  private power(): Expr {
    const base = this.postfix();
    if (this.isOp("**")) {
      const op = this.next();
      return { k: "bin", op: "**", l: base, r: this.factor(), line: op.line };
    }
    return base;
  }

  private postfix(): Expr {
    const startOffset = this.peek().start;
    let expr = this.atom();
    for (;;) {
      if (this.isOp("(")) {
        const open = this.next();
        expr = { k: "call", fn: expr, args: this.arguments(), line: open.line };
      } else if (this.isOp("[")) {
        const open = this.next();
        expr = { k: "index", obj: expr, idx: this.subscript(), line: open.line };
      } else if (this.isOp(".")) {
        this.next();
        const nameToken = this.peek();
        if (nameToken.type !== "NAME" || KEYWORDS.has(nameToken.text)) this.invalid();
        this.next();
        if (!this.isOp("(")) {
          throw new UnsupportedError(
            "attributes (only list methods such as a.append(x) work)",
            nameToken.line,
          );
        }
        const objText = this.source.slice(startOffset, this.tokens[this.pos - 3].end);
        this.next();
        expr = {
          k: "method",
          obj: expr,
          objText,
          name: nameToken.text,
          args: this.arguments(),
          line: nameToken.line,
        };
      } else {
        return expr;
      }
    }
  }

  /** After `(`: comma-separated positional arguments up to `)`. */
  private arguments(): Expr[] {
    const args: Expr[] = [];
    while (!this.isOp(")")) {
      if (this.isOp("*") || this.isOp("**")) {
        throw new UnsupportedError("*args and **kwargs", this.peek().line);
      }
      if (this.peek().type === "NAME" && this.isOp("=", 1)) {
        throw new UnsupportedError("keyword arguments (like end=...)", this.peek().line);
      }
      args.push(this.expression());
      if (this.isName("for")) throw new UnsupportedError("comprehensions", this.peek().line);
      if (this.isOp(",")) this.next();
      else if (!this.isOp(")")) this.invalid();
    }
    this.next();
    return args;
  }

  private subscript(): Expr {
    if (this.isOp(":")) throw new UnsupportedError("slicing (a[i:j])", this.peek().line);
    const idx = this.expression();
    if (this.isOp(":")) throw new UnsupportedError("slicing (a[i:j])", this.peek().line);
    this.expectOp("]");
    return idx;
  }

  private atom(): Expr {
    const token = this.peek();
    switch (token.type) {
      case "NUMBER":
        this.next();
        return { k: "num", v: parseNumber(token.text), line: token.line };
      case "STRING": {
        this.next();
        if (this.peek().type === "STRING") {
          throw new UnsupportedError("two string literals side by side", token.line);
        }
        return { k: "str", v: token.text, line: token.line };
      }
      case "NAME": {
        if (token.text === "True" || token.text === "False") {
          this.next();
          return { k: "const", v: token.text === "True", line: token.line };
        }
        if (token.text === "None") {
          this.next();
          return { k: "const", v: null, line: token.line };
        }
        const unsupported = UNSUPPORTED_STATEMENTS[token.text];
        if (unsupported) throw new UnsupportedError(unsupported, token.line);
        if (KEYWORDS.has(token.text)) this.invalid();
        this.next();
        return { k: "name", id: token.text, line: token.line };
      }
      case "OP":
        if (token.text === "(") {
          this.next();
          if (this.isOp(")")) throw new UnsupportedError("tuples", token.line);
          const inner = this.expression();
          if (this.isOp(",")) throw new UnsupportedError("tuples", token.line);
          this.expectOp(")");
          return inner;
        }
        if (token.text === "[") {
          this.next();
          const items: Expr[] = [];
          while (!this.isOp("]")) {
            items.push(this.expression());
            if (this.isName("for"))
              throw new UnsupportedError("list comprehensions", this.peek().line);
            if (this.isOp(",")) this.next();
            else if (!this.isOp("]")) this.invalid();
          }
          this.next();
          return { k: "list", items, line: token.line };
        }
        return this.invalid();
      default:
        return this.invalid();
    }
  }
}

function parseNumber(text: string): bigint | number {
  return /^\d+$/.test(text) ? BigInt(text) : Number(text);
}
