"use client";

/** A short Python snippet with its (pre-verified) output underneath. No Run button: one less tap. */

import { PythonSource } from "../../tutorials/components/tutorial-blocks";
import type { Snippet } from "../mock-data";

export function CodeSnippet({ snippet }: { snippet: Snippet }) {
  return (
    <figure className="overflow-hidden rounded-lg border border-border bg-muted/40">
      <PythonSource code={snippet.source} className="py-3 text-[0.85rem] sm:text-[0.95rem]" />
      <figcaption className="border-border border-t bg-muted/60 px-4 py-2.5">
        <span className="block font-mono text-[0.68rem] text-muted-foreground uppercase tracking-widest">
          Output
        </span>
        <pre className="mt-1 font-mono text-[0.85rem] text-foreground leading-6 sm:text-[0.95rem]">
          {snippet.output}
        </pre>
      </figcaption>
    </figure>
  );
}
