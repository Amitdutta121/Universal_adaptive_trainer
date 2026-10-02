import { cn } from "@/lib/utils";
import { PythonSource } from "../../tutorials/components/tutorial-blocks";

/** A Python snippet in a bordered block, with its (real) output underneath when there is one. */
export function SnippetBlock({
  code,
  output,
  className,
}: {
  code: string;
  output?: string;
  className?: string;
}) {
  return (
    <figure className={cn("overflow-hidden rounded-lg border border-border bg-muted/60", className)}>
      <PythonSource code={code} className="py-3" />
      {output !== undefined ? (
        <figcaption className="border-border border-t bg-background/60 px-4 py-2.5">
          <span className="block font-mono text-[0.68rem] text-muted-foreground uppercase tracking-widest">
            Output
          </span>
          <pre className="mt-1 overflow-x-auto font-mono text-[0.82rem] text-foreground leading-6">
            {output}
          </pre>
        </figcaption>
      ) : null}
    </figure>
  );
}
