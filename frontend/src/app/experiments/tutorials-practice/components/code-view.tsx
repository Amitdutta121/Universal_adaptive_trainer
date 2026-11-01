"use client";

/**
 * Small presentational pieces shared by the practice screen and the simulator: inline `code` in a
 * sentence, numbered source lines with the current line marked, and a static snippet with output.
 * Highlighting comes from the shared read-only tokenizer.
 */

import { Fragment, type ReactNode, useMemo } from "react";
import { cn } from "@/lib/utils";
import { tokenizePython } from "../../tutorials/components/tutorial-blocks";

// The tokenizer's colour map is not exported by the shared file, so it is repeated here.
const TOKEN_CLASS = {
  comment: "text-muted-foreground italic",
  string: "text-emerald-700 dark:text-emerald-400",
  number: "text-amber-700 dark:text-amber-400",
  keyword: "font-medium text-primary",
  builtin: "text-sky-700 dark:text-sky-400",
  plain: "",
} as const;

/** `code` spans inside plain text. Nothing else is interpreted. */
export function Inline({ text }: { text: string }): ReactNode {
  const parts = text.split(/(`[^`]+`)/g).filter(Boolean);
  return (
    <>
      {parts.map((part, index) => {
        const key = `${index}:${part}`;
        if (part.startsWith("`") && part.endsWith("`")) {
          return (
            <code
              key={key}
              className="rounded bg-muted px-1 py-0.5 font-mono text-[0.86em] text-foreground"
            >
              {part.slice(1, -1)}
            </code>
          );
        }
        return <Fragment key={key}>{part}</Fragment>;
      })}
    </>
  );
}

export function CodeLines({
  code,
  currentLine = null,
  errorLine = false,
  numbers = true,
}: {
  code: string;
  /** 1-based line to mark; null marks none. */
  currentLine?: number | null;
  /** Colour the marked line as the one that failed. */
  errorLine?: boolean;
  /** Show the line-number gutter. */
  numbers?: boolean;
}) {
  const lines = useMemo(
    () =>
      code
        .replace(/\n$/, "")
        .split("\n")
        .map((text) => tokenizePython(text)),
    [code],
  );
  return (
    <ol className="font-mono text-[0.84rem] leading-6">
      {lines.map((tokens, position) => {
        const number = position + 1;
        const current = number === currentLine;
        return (
          <li
            // biome-ignore lint/suspicious/noArrayIndexKey: source lines never reorder
            key={position}
            aria-current={current ? "step" : undefined}
            className={cn(
              "flex border-transparent border-l-2 pr-3",
              current &&
                (errorLine ? "border-destructive bg-destructive/10" : "border-primary bg-accent"),
            )}
          >
            {numbers ? (
              <span
                aria-hidden="true"
                className="w-8 shrink-0 select-none pr-2.5 text-right text-muted-foreground"
              >
                {number}
              </span>
            ) : (
              <span aria-hidden="true" className="w-2 shrink-0" />
            )}
            <code className="whitespace-pre">
              {tokens.length === 0 ? " " : null}
              {tokens.map((token) => (
                <span key={token.at} className={TOKEN_CLASS[token.kind]}>
                  {token.text}
                </span>
              ))}
            </code>
          </li>
        );
      })}
    </ol>
  );
}

/** A read-only snippet in a bordered block, with output underneath when given. */
export function CodeBlock({
  code,
  output,
  label,
  className,
}: {
  code: string;
  output?: string;
  /** Accessible name for the block. */
  label: string;
  className?: string;
}) {
  return (
    <figure
      aria-label={label}
      className={cn("m-0 overflow-hidden rounded-lg border border-border bg-muted/60", className)}
    >
      <div className="overflow-x-auto py-2.5">
        <CodeLines code={code} />
      </div>
      {output !== undefined ? (
        <figcaption className="border-border border-t bg-background/60 px-3 py-2">
          <span className="block font-mono text-[0.68rem] text-muted-foreground uppercase tracking-widest">
            Output
          </span>
          <pre className="mt-1 overflow-x-auto font-mono text-[0.82rem] text-foreground leading-6">
            {output.trimEnd() || "(nothing)"}
          </pre>
        </figcaption>
      ) : null}
    </figure>
  );
}
