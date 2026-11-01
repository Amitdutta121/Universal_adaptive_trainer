/**
 * The caveats a document declared about itself.
 *
 * Severity is shown because it is the difference between "this book is missing
 * something" and "this is true and worth knowing": only a `defect` makes a book
 * partial, and a badge that fires on every informational warning teaches the
 * professor to ignore all of them.
 */

import { Info, TriangleAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { ExtractionWarning } from "@/lib/api/types";
import { codeLabel } from "@/lib/display";

export function WarningList({ warnings }: { warnings: readonly ExtractionWarning[] }) {
  if (warnings.length === 0) return null;

  return (
    <ul className="space-y-2">
      {warnings.map((warning, index) => {
        const isDefect = warning.severity === "defect";
        return (
          <li
            // Warnings carry no id and may legitimately repeat a code.
            // biome-ignore lint/suspicious/noArrayIndexKey: the list is static per render
            key={`${warning.code}-${index}`}
            className="flex items-start gap-2 rounded-md border p-3 text-sm"
          >
            {isDefect ? (
              <TriangleAlert className="mt-0.5 size-4 shrink-0 text-destructive" />
            ) : (
              <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            )}
            <div className="min-w-0 space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={isDefect ? "destructive" : "outline"}>
                  {codeLabel(warning.code)}
                </Badge>
                {warning.location ? (
                  <span className="text-muted-foreground text-xs">{warning.location}</span>
                ) : null}
              </div>
              <p className="text-foreground">{warning.message}</p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
