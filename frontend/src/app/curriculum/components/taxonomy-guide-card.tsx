"use client";

/**
 * The reference material behind a taxonomy document: the prompt that produces
 * one, a worked example, and the limits the validator enforces.
 *
 * All three come from `GET /api/curriculum/document-guide`, which renders them
 * from the taxonomy contract itself, so nothing here can describe a document the
 * validator would refuse. All three are collapsed: they are read once, while a
 * document is being produced, and are noise on every later visit.
 *
 * Where the books guide lists three closed vocabularies, a taxonomy document has
 * none — so what takes their place is the field reference, which is the part a
 * professor cannot guess.
 */

import { CollapsiblePanel } from "@/components/collapsible-panel";
import { CopyButton } from "@/components/copy-button";
import { QueryError } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { TaxonomyDocumentGuide } from "@/lib/api/types";

function bound(field: TaxonomyDocumentGuide["fields"][number]): string {
  if (field.kind === "list") {
    return field.min_length ? `at least ${field.min_length}` : "a list";
  }
  if (field.max_length === null) return "";
  return field.min_length
    ? `${field.min_length}–${field.max_length} characters`
    : `up to ${field.max_length} characters`;
}

function FieldReference({ fields }: { fields: TaxonomyDocumentGuide["fields"] }) {
  return (
    <dl className="space-y-2">
      {fields.map((field) => (
        <div key={field.path} className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <dt>
            <Badge variant="outline" className="font-mono text-[11px]">
              {field.path}
            </Badge>
          </dt>
          <dd className="text-muted-foreground text-sm">
            <span className="text-foreground">
              {field.required ? "required" : "optional"}
              {bound(field) ? `, ${bound(field)}` : ""}
            </span>{" "}
            — {field.meaning}
          </dd>
        </div>
      ))}
    </dl>
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

export function TaxonomyGuideCard({
  guide,
  isPending,
  error,
}: {
  guide: TaxonomyDocumentGuide | undefined;
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
        summary="Paste it into Claude or ChatGPT above your syllabus, then upload what comes back."
        openLabel="Show prompt"
        actions={<CopyButton text={guide.prompt} label="Copy prompt" copiedLabel="Copied" />}
      >
        <Pre wrap>{guide.prompt}</Pre>
      </CollapsiblePanel>

      <CollapsiblePanel
        title="Example document"
        summary={`A complete taxonomy this application accepts — schema version ${guide.schema_version}.`}
        openLabel="Show example"
        actions={<CopyButton text={guide.example_json} label="Copy example" copiedLabel="Copied" />}
      >
        <Pre>{guide.example_json}</Pre>
      </CollapsiblePanel>

      <CollapsiblePanel
        title="What the validator requires"
        summary="Every field and every limit. An unknown key is rejected, not ignored."
        openLabel="Show fields"
      >
        <div className="space-y-4">
          <FieldReference fields={guide.fields} />
          <p className="text-muted-foreground text-sm">
            Topic names must be unique, and subtopic names unique within their topic. Names are
            compared ignoring case, spacing and punctuation, so two spellings of one name count as a
            duplicate and the document is refused.
          </p>
        </div>
      </CollapsiblePanel>
    </div>
  );
}
