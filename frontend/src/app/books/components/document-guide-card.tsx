"use client";

/**
 * The reference material behind a book document: the prompt that produces one,
 * a worked example, and the values the validator will accept.
 *
 * All three come from `GET /api/books/document-guide`, which renders them from
 * the ingestion contract itself, so nothing here can describe a document the
 * validator would refuse. All three are collapsed: they are read once, while a
 * document is being produced, and are noise on every later visit.
 *
 * The prompt is advisory. A reply that followed it is validated on upload exactly
 * like any other.
 */

import { CollapsiblePanel } from "@/components/collapsible-panel";
import { CopyButton } from "@/components/copy-button";
import { QueryError } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { BookDocumentGuide } from "@/lib/api/types";

function Vocabulary({
  title,
  terms,
}: {
  title: string;
  terms: BookDocumentGuide["structure_sources"];
}) {
  return (
    <div className="space-y-2">
      <h4 className="font-medium text-sm">{title}</h4>
      <dl className="space-y-1.5">
        {terms.map((term) => (
          <div key={term.value} className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <dt>
              <Badge variant="outline" className="font-mono text-[11px]">
                {term.value}
              </Badge>
            </dt>
            <dd className="text-muted-foreground text-sm">{term.meaning}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/**
 * A capped, scrollable block.
 *
 * `wrap` is on for the prompt — it is prose, meant to be read here before it is
 * copied — and off for the example, where a wrapped line would misrepresent the
 * JSON's shape.
 */
function Pre({ children, wrap = false }: { children: string; wrap?: boolean }) {
  return (
    <pre
      className={`max-h-[24rem] overflow-auto rounded-md border bg-muted/50 p-3 font-mono text-xs leading-relaxed ${
        wrap ? "whitespace-pre-wrap break-words" : ""
      }`}
    >
      {children}
    </pre>
  );
}

export function DocumentGuideCard({
  guide,
  isPending,
  error,
}: {
  guide: BookDocumentGuide | undefined;
  isPending: boolean;
  error: unknown;
}) {
  if (error) return <QueryError error={error} />;
  if (isPending) return <Skeleton className="h-[6rem] w-full" />;
  if (!guide) return null;

  return (
    <div className="space-y-2">
      <CollapsiblePanel
        title="Prompt for an assistant"
        summary="Paste it into Claude or ChatGPT above your textbook text, then import what comes back."
        openLabel="Show prompt"
        actions={<CopyButton text={guide.prompt} label="Copy prompt" copiedLabel="Copied" />}
      >
        <Pre wrap>{guide.prompt}</Pre>
      </CollapsiblePanel>

      <CollapsiblePanel
        title="Example document"
        summary={`A complete document this application accepts — schema version ${guide.schema_version}.`}
        openLabel="Show example"
        actions={<CopyButton text={guide.example_json} label="Copy example" copiedLabel="Copied" />}
      >
        <Pre>{guide.example_json}</Pre>
      </CollapsiblePanel>

      <CollapsiblePanel
        title="Allowed values"
        summary="Closed vocabularies. Any other value is rejected on upload."
        openLabel="Show values"
      >
        <div className="space-y-4">
          <Vocabulary title="structure_source" terms={guide.structure_sources} />
          <Vocabulary title="warning code" terms={guide.warning_codes} />
          <Vocabulary title="warning severity" terms={guide.warning_severities} />
        </div>
      </CollapsiblePanel>
    </div>
  );
}
