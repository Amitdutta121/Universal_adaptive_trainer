/**
 * One chunk's text, with the citation that makes it traceable.
 *
 * A server component: nothing here is edited, so there is no reason to ship the
 * fetch to the browser. The text is rendered pre-wrapped because a chunk may hold a
 * code listing, and collapsing that whitespace would destroy it. Any version of the
 * book's chunks resolves here, so a link from an older question still opens.
 */

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { PageHeader } from "@/components/page-header";
import { QueryError } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, api, readApiError, unwrap } from "@/lib/api/client";
import { courseRequestHeaders } from "@/lib/api/server-request";
import type { Schemas } from "@/lib/api/types";
import { coursePath } from "@/lib/course";

export const dynamic = "force-dynamic";

export default async function ChunkPage(
  props: PageProps<"/courses/[courseId]/books/[book_id]/chunks/[chunk_id]">,
) {
  const { courseId, book_id, chunk_id } = await props.params;
  const bookId = Number(book_id);
  if (!Number.isInteger(bookId)) notFound();

  let chunk: Schemas["ChunkOut"];
  try {
    chunk = await unwrap(
      api.GET("/api/chunks/{chunk_id}", {
        params: { path: { chunk_id } },
        headers: await courseRequestHeaders(courseId),
      }),
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    return (
      <>
        <PageHeader title="Chunk" />
        <QueryError error={readApiError(error)} />
      </>
    );
  }
  // The URL asserts the chunk belongs to this book.
  if (chunk.book_id !== bookId) notFound();

  return (
    <>
      <PageHeader
        title={chunk.heading_path.at(-1) ?? `Chunk ${chunk.ordinal + 1}`}
        summary={chunk.citation}
        actions={
          <Badge variant="outline" className="font-mono text-[11px]">
            version {chunk.book_version}
          </Badge>
        }
      />

      <Link
        href={coursePath(courseId, `/books/${bookId}`)}
        className="flex w-fit items-center gap-1 text-muted-foreground text-sm hover:underline"
      >
        <ArrowLeft className="size-3" />
        Back to the book
      </Link>

      <Card>
        <CardHeader>
          <CardTitle>Chunk text</CardTitle>
          <CardDescription>
            {chunk.text.length.toLocaleString()} characters, as parsed from the book file.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-md border bg-muted/40 p-4 font-mono text-xs leading-relaxed">
            {chunk.text}
          </pre>
        </CardContent>
      </Card>
    </>
  );
}
