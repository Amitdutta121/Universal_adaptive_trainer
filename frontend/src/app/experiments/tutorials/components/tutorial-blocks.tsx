"use client";

/**
 * The pieces a tutorial is made of: inline text, a highlighted code block with a Run button,
 * callouts, and a "check yourself" question. All presentational; the tutorial's content and the
 * reading state live above.
 */

import { CircleAlert, Lightbulb, Play, Sparkles, Terminal } from "lucide-react";
import { Fragment, useId, useState } from "react";
import { CopyButton } from "@/components/copy-button";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Block, CalloutTone, CheckOption } from "../mock-tutorials";

// ---- inline text ----------------------------------------------------------------------------

/** `code` and **bold** only. Anything else in a tutorial's text is plain. */
export function Inline({ text }: { text: string }) {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).filter(Boolean);
  return (
    <>
      {parts.map((part, index) => {
        const key = `${index}:${part}`;
        if (part.startsWith("`")) {
          return (
            <code
              key={key}
              className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.86em] text-foreground"
            >
              {part.slice(1, -1)}
            </code>
          );
        }
        if (part.startsWith("**")) {
          return (
            <strong key={key} className="font-semibold text-foreground">
              {part.slice(2, -2)}
            </strong>
          );
        }
        return <Fragment key={key}>{part}</Fragment>;
      })}
    </>
  );
}

// ---- Python highlighting ---------------------------------------------------------------------

const KEYWORDS = new Set([
  "and", "as", "break", "class", "continue", "def", "elif", "else", "for", "from", "if",
  "import", "in", "is", "not", "or", "pass", "return", "while", "True", "False", "None",
]);
const BUILTINS = new Set([
  "print", "range", "len", "type", "int", "float", "str", "bool", "input", "enumerate", "sum",
]);

type Token = { at: number; text: string; kind: "comment" | "string" | "number" | "keyword" | "builtin" | "plain" };

const TOKEN = /(#[^\n]*)|("(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*')|(\b\d+(?:\.\d+)?\b)|(\b[A-Za-z_]\w*\b)/g;

/** A small tokenizer: enough for teaching snippets, not a Python parser. f-strings are one string. */
export function tokenizePython(source: string): Token[] {
  const tokens: Token[] = [];
  let last = 0;
  for (const match of source.matchAll(TOKEN)) {
    const at = match.index ?? 0;
    if (at > last) tokens.push({ at: last, text: source.slice(last, at), kind: "plain" });
    const [text, comment, string, number, word] = match;
    let kind: Token["kind"] = "plain";
    if (comment) kind = "comment";
    else if (string) kind = "string";
    else if (number) kind = "number";
    else if (word) kind = KEYWORDS.has(word) ? "keyword" : BUILTINS.has(word) ? "builtin" : "plain";
    tokens.push({ at, text, kind });
    last = at + text.length;
  }
  if (last < source.length) tokens.push({ at: last, text: source.slice(last), kind: "plain" });
  return tokens;
}

const TOKEN_CLASS: Record<Token["kind"], string> = {
  comment: "text-muted-foreground italic",
  string: "text-emerald-700 dark:text-emerald-400",
  number: "text-amber-700 dark:text-amber-400",
  keyword: "font-medium text-primary",
  builtin: "text-sky-700 dark:text-sky-400",
  plain: "",
};

export function PythonSource({ code, className }: { code: string; className?: string }) {
  return (
    <pre
      className={cn(
        "overflow-x-auto px-4 py-3.5 font-mono text-[0.82rem] text-foreground leading-6",
        className,
      )}
    >
      <code>
        {tokenizePython(code).map((token) => (
          <span key={token.at} className={TOKEN_CLASS[token.kind]}>
            {token.text}
          </span>
        ))}
      </code>
    </pre>
  );
}

// ---- code block with output -----------------------------------------------------------------

export function CodeBlock({
  title,
  code,
  output,
  note,
}: {
  title?: string;
  code: string;
  output?: string;
  note?: string;
}) {
  const [ran, setRan] = useState(false);
  const outputId = useId();

  return (
    <figure className="my-5 overflow-hidden rounded-lg border border-border bg-card">
      <figcaption className="flex items-center justify-between gap-2 border-border border-b bg-muted/50 py-1.5 pr-1.5 pl-4">
        <span className="font-mono text-muted-foreground text-xs">{title ?? "example.py"}</span>
        <span className="flex items-center gap-1">
          <CopyButton text={code} variant="ghost" size="xs" />
          {output !== undefined ? (
            <Button
              type="button"
              size="xs"
              variant={ran ? "secondary" : "default"}
              aria-expanded={ran}
              aria-controls={outputId}
              onClick={() => setRan((value) => !value)}
            >
              <Play aria-hidden="true" />
              {ran ? "Hide output" : "Run"}
            </Button>
          ) : null}
        </span>
      </figcaption>
      <PythonSource code={code} />
      {output === undefined && note ? (
        <p className="flex items-start gap-2 border-border border-t bg-muted/40 px-4 py-2 text-muted-foreground text-xs">
          <CircleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          {note}
        </p>
      ) : null}
      {output !== undefined && ran ? (
        <div id={outputId} className="border-border border-t bg-muted/40">
          <p className="flex items-center gap-1.5 px-4 pt-2 font-mono text-[0.68rem] text-muted-foreground uppercase tracking-widest">
            <Terminal className="size-3" aria-hidden="true" />
            Output
          </p>
          <pre className="overflow-x-auto px-4 pt-1 pb-3 font-mono text-[0.82rem] text-foreground leading-6">
            {output}
          </pre>
        </div>
      ) : null}
    </figure>
  );
}

// ---- callouts ---------------------------------------------------------------------------------

const TONE: Record<CalloutTone, { label: string; icon: typeof Lightbulb; bar: string; text: string }> = {
  idea: { label: "Key idea", icon: Lightbulb, bar: "border-primary", text: "text-primary" },
  mistake: {
    label: "Common mistake",
    icon: CircleAlert,
    bar: "border-amber-500",
    text: "text-amber-700 dark:text-amber-400",
  },
  tip: { label: "Tip", icon: Sparkles, bar: "border-sky-500", text: "text-sky-700 dark:text-sky-400" },
};

export function Callout({ tone, title, text }: { tone: CalloutTone; title: string; text: string }) {
  const { label, icon: Icon, bar, text: labelColour } = TONE[tone];
  return (
    <aside className={cn("my-5 border-l-2 py-1 pl-4", bar)} aria-label={label}>
      <p className={cn("flex items-center gap-1.5 font-mono text-[0.68rem] uppercase tracking-widest", labelColour)}>
        <Icon className="size-3.5" aria-hidden="true" />
        {label}
      </p>
      <p className="mt-1 font-heading font-semibold text-foreground">{title}</p>
      <p className="mt-1 text-muted-foreground leading-7">
        <Inline text={text} />
      </p>
    </aside>
  );
}

// ---- check yourself -----------------------------------------------------------------------------

export function CheckYourself({
  question,
  code,
  options,
  onAnswered,
}: {
  question: string;
  code?: string;
  options: CheckOption[];
  onAnswered: (correct: boolean) => void;
}) {
  const [picked, setPicked] = useState<number | null>(null);
  const groupId = useId();
  const chosen = picked === null ? null : options[picked];

  return (
    <fieldset className="my-6 min-w-0 rounded-lg border border-border bg-card p-4 sm:p-5">
      <legend className="sr-only">Check yourself: {question.replaceAll("`", "")}</legend>
      <p className="font-mono text-[0.68rem] text-muted-foreground uppercase tracking-widest">
        Check yourself
      </p>
      <p className="mt-1 font-heading font-semibold text-foreground">
        <Inline text={question} />
      </p>
      {code ? (
        <div className="mt-3 overflow-hidden rounded-md border border-border bg-muted/40">
          <PythonSource code={code} />
        </div>
      ) : null}

      <div className="mt-3 grid gap-2">
        {options.map((option, index) => {
          const selected = picked === index;
          return (
            <label
              key={option.text}
              className={cn(
                "flex cursor-pointer items-center gap-3 rounded-md border px-3 py-2 text-sm transition-colors",
                "has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring/50",
                !selected && "border-border bg-background hover:bg-muted",
                selected && option.correct && "border-emerald-600/60 bg-emerald-600/10",
                selected && !option.correct && "border-destructive/60 bg-destructive/10",
              )}
            >
              <input
                type="radio"
                name={groupId}
                className="sr-only"
                checked={selected}
                onChange={() => {
                  setPicked(index);
                  onAnswered(Boolean(option.correct));
                }}
              />
              <span
                aria-hidden="true"
                className="flex size-5 shrink-0 items-center justify-center rounded-full border border-border font-mono text-[0.68rem] text-muted-foreground"
              >
                {String.fromCharCode(65 + index)}
              </span>
              <span className="min-w-0 font-mono text-[0.82rem]">{option.text}</span>
            </label>
          );
        })}
      </div>

      <div role="status" aria-live="polite" className="mt-3 min-h-6 text-sm">
        {chosen ? (
          <p className={cn("leading-6", chosen.correct ? "text-emerald-700 dark:text-emerald-400" : "text-foreground")}>
            <strong className="font-semibold">{chosen.correct ? "Correct. " : "Not quite. "}</strong>
            <Inline text={chosen.why} />
            {chosen.correct ? null : <span className="text-muted-foreground"> Try another.</span>}
          </p>
        ) : null}
      </div>
    </fieldset>
  );
}

// ---- dispatcher ---------------------------------------------------------------------------------

/** A block has no id of its own, so its key is made from what makes it different from its neighbours. */
export function blockKey(block: Block): string {
  switch (block.kind) {
    case "p":
      return `p:${block.text}`;
    case "list":
      return `list:${block.items.join("|")}`;
    case "code":
      return `code:${block.code}`;
    case "callout":
      return `callout:${block.title}`;
    case "check":
      return `check:${block.id}`;
  }
}

export function BlockView({
  block,
  onChecked,
  onCite,
}: {
  block: Block;
  onChecked: (id: string, correct: boolean) => void;
  onCite: (n: number) => void;
}) {
  switch (block.kind) {
    case "p":
      return (
        <p className="my-4 text-foreground/90 leading-7">
          <Inline text={block.text} />
          {block.cite ? (
            <button
              type="button"
              onClick={() => onCite(block.cite as number)}
              className="ml-1 align-super font-mono text-[0.68rem] text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label={`Source ${block.cite}`}
            >
              [{block.cite}]
            </button>
          ) : null}
        </p>
      );
    case "list":
      return (
        <ul className="my-4 grid gap-1.5 pl-1">
          {block.items.map((item) => (
            <li key={item} className="flex gap-2.5 leading-7">
              <span className="mt-3 size-1 shrink-0 rounded-full bg-primary" aria-hidden="true" />
              <span>
                <Inline text={item} />
              </span>
            </li>
          ))}
        </ul>
      );
    case "code":
      return <CodeBlock title={block.title} code={block.code} output={block.output} note={block.note} />;
    case "callout":
      return <Callout tone={block.tone} title={block.title} text={block.text} />;
    case "check":
      return (
        <CheckYourself
          question={block.question}
          code={block.code}
          options={block.options}
          onAnswered={(correct) => onChecked(block.id, correct)}
        />
      );
  }
}
