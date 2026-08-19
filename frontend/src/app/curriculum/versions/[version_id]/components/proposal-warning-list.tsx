/**
 * Caveats a legacy LLM proposal recorded about itself.
 *
 * Legacy-only. An uploaded taxonomy always records an empty list, and the screen
 * gates this card on the version's provenance rather than on that emptiness, so
 * the section cannot appear for an upload even if the field were populated.
 *
 * Unlike a book's extraction warnings, a `DisplayProposalWarning` carries no
 * severity — so every entry gets one neutral icon rather than being sorted into
 * defects and facts.
 */

import { Info } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { ProposalWarning } from "@/lib/api/types";
import { codeLabel } from "@/lib/display";

export function ProposalWarningList({ warnings }: { warnings: readonly ProposalWarning[] }) {
  if (warnings.length === 0) return null;

  return (
    <ul className="space-y-2">
      {warnings.map((warning, index) => (
        <li
          // biome-ignore lint/suspicious/noArrayIndexKey: warnings carry no identity
          key={`${warning.code}-${index}`}
          className="flex flex-wrap items-baseline gap-2 border-b pb-2 text-sm last:border-b-0"
        >
          <Info className="size-4 shrink-0 self-center text-muted-foreground" />
          <span>{warning.message}</span>
          {warning.location ? (
            <span className="text-muted-foreground text-xs">{warning.location}</span>
          ) : null}
          <Badge variant="outline" className="ml-auto">
            {codeLabel(warning.code)}
          </Badge>
        </li>
      ))}
    </ul>
  );
}
