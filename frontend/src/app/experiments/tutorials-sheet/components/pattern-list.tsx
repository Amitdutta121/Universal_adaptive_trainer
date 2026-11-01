import { ArrowRight } from "lucide-react";
import { PythonSource } from "../../tutorials/components/tutorial-blocks";
import type { Pattern } from "../mock-data";

/** The cheat-sheet rows: what it is for, the code, and what it gives, side by side. */
export function PatternList({ patterns }: { patterns: readonly Pattern[] }) {
  return (
    <ul aria-label="Patterns" className="divide-y divide-border border-border border-y">
      {patterns.map((pattern) => (
        <li
          key={pattern.id}
          className="grid gap-x-4 gap-y-1.5 py-2.5 sm:grid-cols-[7.5rem_minmax(0,1fr)] sm:items-center"
        >
          <span className="text-muted-foreground text-sm">{pattern.label}</span>
          <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1.5">
            <PythonSource
              code={pattern.code}
              className="rounded-md bg-muted px-2.5 py-1.5 text-[0.82rem] leading-6"
            />
            <ArrowRight className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
            <span className="sr-only">gives</span>
            <span className="font-medium font-mono text-foreground text-sm">{pattern.result}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}
