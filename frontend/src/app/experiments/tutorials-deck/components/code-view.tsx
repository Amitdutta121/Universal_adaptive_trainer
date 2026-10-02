"use client";

/**
 * The snippet, always on screen: line numbers, the line that just ran marked, lines that were not
 * taken greyed out, and lines waiting for a call to come back marked with a dashed edge.
 */

import { useMemo } from "react";
import { cn } from "@/lib/utils";
import { tokenizePython } from "../../tutorials/components/tutorial-blocks";

// The shared tokenizer does not export its colour map, so this repeats it.
const TOKEN_CLASS = {
  comment: "text-muted-foreground italic",
  string: "text-emerald-700 dark:text-emerald-400",
  number: "text-amber-700 dark:text-amber-400",
  keyword: "font-medium text-primary",
  builtin: "text-sky-700 dark:text-sky-400",
  plain: "",
} as const;

export function CodeView({
  code,
  current = null,
  dim = [],
  paused = [],
  label,
}: {
  code: string;
  /** 1-based line that just ran. */
  current?: number | null;
  /** Lines to grey out: branches that were not taken. */
  dim?: number[];
  /** Lines whose call has not returned yet. */
  paused?: number[];
  label: string;
}) {
  const lines = useMemo(() => code.split("\n").map((text) => tokenizePython(text)), [code]);
  return (
    <fieldset
      aria-label={label}
      className="m-0 min-w-0 overflow-x-auto rounded-lg border-0 bg-muted/50 px-0 py-2 dark:bg-muted/30"
    >
      <ol className="w-max min-w-full font-mono text-[0.84rem] leading-6 sm:text-[0.9rem]">
        {lines.map((tokens, position) => {
          const number = position + 1;
          const isCurrent = number === current;
          const isPaused = !isCurrent && paused.includes(number);
          const isDim = dim.includes(number);
          return (
            <li
              // biome-ignore lint/suspicious/noArrayIndexKey: source lines never reorder
              key={position}
              aria-current={isCurrent ? "step" : undefined}
              data-dim={isDim ? "true" : undefined}
              className={cn(
                "flex border-transparent border-l-2 pr-3",
                isCurrent && "border-primary bg-accent",
                isPaused && "border-muted-foreground/70 border-dashed",
                isDim && "opacity-40",
              )}
            >
              <span
                aria-hidden="true"
                className="w-8 shrink-0 select-none pr-3 text-right text-muted-foreground"
              >
                {number}
              </span>
              <code className="whitespace-pre">
                {tokens.map((token) => (
                  <span key={token.at} className={TOKEN_CLASS[token.kind]}>
                    {token.text}
                  </span>
                ))}
                {tokens.length === 0 ? " " : null}
              </code>
              {isPaused ? <span className="sr-only"> (waiting for the call to return)</span> : null}
            </li>
          );
        })}
      </ol>
    </fieldset>
  );
}
