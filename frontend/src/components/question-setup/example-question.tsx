/**
 * One example question as the professor sees it on a style card: the prompt, the code or
 * options the student gets, and the answer key underneath.
 */

import { CheckIcon, GripVerticalIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ExampleQuestion } from "./types";

const LETTERS = ["A", "B", "C", "D", "E", "F"];

/** A fixed, readable shuffle: odd positions first, then even, so the order is never the key. */
function shuffled(lines: readonly string[]): string[] {
  const odd = lines.filter((_, index) => index % 2 === 1);
  const even = lines.filter((_, index) => index % 2 === 0);
  return [...odd, ...even.reverse()];
}

export function CodeBlock({ code }: { code: string }) {
  return (
    <pre className="overflow-x-auto rounded-md border bg-muted/60 px-3 py-2 font-mono text-[12.5px] leading-relaxed">
      <code>{code}</code>
    </pre>
  );
}

export function ExampleQuestionView({ example, label }: { example: ExampleQuestion; label: string }) {
  // The API sends empty lists where the prototype leaves a field out.
  const lines = example.lines?.length ? example.lines : null;
  const options = example.options?.length ? example.options : null;
  return (
    <figure className="flex min-w-0 flex-col gap-3 rounded-lg border bg-card p-3.5">
      <figcaption className="text-muted-foreground text-xs">{label}</figcaption>
      <p className="text-sm leading-relaxed">{example.prompt}</p>

      {example.code ? <CodeBlock code={example.code} /> : null}

      {lines ? (
        <div className="flex flex-col gap-1">
          <p className="text-muted-foreground text-xs">Students get these lines shuffled:</p>
          <ul className="flex flex-col gap-1">
            {shuffled(lines).map((line) => (
              <li
                key={line}
                className="flex items-center gap-2 rounded-md border bg-background px-2 py-1 font-mono text-[12.5px]"
              >
                <GripVerticalIcon className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
                <span className="whitespace-pre">{line.trimStart()}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {options ? (
        <ul className="flex flex-col gap-1.5">
          {options.map((option, index) => (
            <li
              key={option.text}
              className={cn(
                "flex items-start gap-2 rounded-md border px-2.5 py-1.5 text-sm",
                option.correct && "border-[var(--ok-solid)]/40 bg-[var(--ok-wash)]",
              )}
            >
              <span className="w-4 shrink-0 font-medium text-muted-foreground text-xs leading-5">
                {LETTERS[index]}
              </span>
              <span className="flex-1">{option.text}</span>
              {option.correct ? (
                <CheckIcon className="mt-0.5 size-4 shrink-0 text-[var(--ok-solid)]" aria-label="Correct answer" />
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}

      <div className="mt-auto flex flex-col gap-1 border-t pt-2.5 text-xs">
        {lines ? (
          <div>
            <span className="text-muted-foreground">Solution: </span>
            <CodeBlock code={lines.join("\n")} />
          </div>
        ) : null}
        {example.answer ? (
          <p>
            <span className="text-muted-foreground">Answer key: </span>
            <span className={cn(example.code || example.tests ? "font-mono" : undefined)}>
              {example.answer}
            </span>
          </p>
        ) : null}
        {example.tests ? (
          <p className="text-muted-foreground">Graded by {example.tests} hidden tests, partial credit per test.</p>
        ) : null}
        {example.grounding ? (
          <p className="text-muted-foreground">Grounded in {example.grounding}</p>
        ) : null}
      </div>
    </figure>
  );
}
