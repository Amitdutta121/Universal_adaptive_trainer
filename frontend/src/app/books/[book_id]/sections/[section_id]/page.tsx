/**
 * One section's text, verbatim, with the citation that makes it traceable.
 *
 * A server component: nothing here is edited, so there is no reason to ship the
 * fetch to the browser. The text is rendered pre-wrapped because it is stored
 * exactly as the document declared it — a section may open with an indented code
 * listing, and collapsing that whitespace would destroy it.
 */

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { PageHeader } from "@/components/page-header";
import { QueryError } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, api, unwrap } from "@/lib/api/client";
import type { Schemas } from "@/lib/api/types";

export const dynamic = "force-dynamic";

export default async function SectionPage(
  props: PageProps<"/books/[book_id]/sections/[section_id]">,
) {
  const { book_id, section_id } = await props.params;
  const bookId = Number(book_id);
  const sectionId = Number(section_id);
  if (!Number.isInteger(bookId) || !Number.isInteger(sectionId)) notFound();

  let detail: Schemas["SectionDetail"];
  try {
    detail = await unwrap(
      api.GET("/api/books/{book_id}/sections/{section_id}", {
        params: { path: { book_id: bookId, section_id: sectionId } },
      }),
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    return (
      <>
        <PageHeader title="Section" />
        <QueryError error={error} />
      </>
    );
  }

  const { section, text, warnings, citation } = detail;

  return (
    <>
      <PageHeader
        title={section.display_title}
        summary={citation}
        actions={
          <>
            {section.structure_confidence !== "high" ? (
              <Badge variant="outline">{section.structure_confidence} confidence</Badge>
            ) : null}
            <Badge variant="outline" className="font-mono text-[11px]">
              {section.structure_source.replace(/_/g, " ")}
            </Badge>
          </>
        }
      />

      <Link
        href={`/books/${bookId}`}
        className="flex w-fit items-center gap-1 text-muted-foreground text-sm hover:underline"
      >
        <ArrowLeft className="size-3" />
        Back to the book
      </Link>

      {warnings.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Declared warnings</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1 text-sm">
              {warnings.map((warning) => (
                <li key={`${warning.code}-${warning.message}`}>
                  <span className="font-mono text-xs">{warning.code}</span> — {warning.message}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Section text</CardTitle>
          <CardDescription>
            {section.char_count.toLocaleString()} characters, stored exactly as the document
            declared them.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-md border bg-muted/40 p-4 font-mono text-xs leading-relaxed">
            {text}
          </pre>
        </CardContent>
      </Card>
    </>
  );
}
