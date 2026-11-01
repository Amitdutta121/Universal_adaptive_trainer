/** Small presentational pieces shared by the steps: inline code, a code box, an output box. */

import { Fragment } from "react";
import { PythonSource } from "../../tutorials/components/tutorial-blocks";

/** `code` only; anything else in an insight is plain text. */
export function Inline({ text }: { text: string }) {
  const parts = text.split(/(`[^`]+`)/g).filter(Boolean);
  return (
    <>
      {parts.map((part, index) => {
        const key = `${index}:${part}`;
        return part.startsWith("`") ? (
          <code key={key} className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.86em] text-foreground">
            {part.slice(1, -1)}
          </code>
        ) : (
          <Fragment key={key}>{part}</Fragment>
        );
      })}
    </>
  );
}

/** A highlighted Python snippet in a bordered box (no title bar, no Run button: it is the question). */
export function CodeBox({ code, label }: { code: string; label?: string }) {
  return (
    <figure
      aria-label={label}
      className="overflow-hidden rounded-lg border border-border bg-card"
    >
      <PythonSource code={code} />
    </figure>
  );
}

/** What Python printed. Muted background so it reads as output, not as code to edit. */
export function OutputBox({
  children,
  label,
  className,
}: {
  children: string;
  label: string;
  className?: string;
}) {
  return (
    <div className={className}>
      <p className="mb-1 font-mono text-[0.68rem] text-muted-foreground uppercase tracking-widest">
        {label}
      </p>
      <pre className="overflow-x-auto whitespace-pre-wrap break-all rounded-lg border border-border bg-muted/50 px-4 py-3 font-mono text-[0.82rem] text-foreground leading-6">
        {children}
      </pre>
    </div>
  );
}
