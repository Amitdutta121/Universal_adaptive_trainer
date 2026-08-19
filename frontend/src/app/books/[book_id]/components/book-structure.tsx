/**
 * The chapter → section tree, exactly as the document declared it.
 *
 * Three things are flagged, and each is a fact the document stated rather than a
 * judgement made here: a unit with no heading in the source (labelled by number or
 * page range, never by an invented title), a boundary the producer guessed at, and
 * a section with no text.
 */

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { ChapterOut, SectionSummary } from "@/lib/api/types";

function chapterLabel(chapter: ChapterOut): string {
  const printed = [chapter.number, chapter.title].filter(Boolean).join(" ");
  return printed || chapter.location_label || "Untitled chapter";
}

function SectionRow({ bookId, section }: { bookId: number; section: SectionSummary }) {
  return (
    <li className="flex flex-wrap items-center gap-2 border-t py-2 text-sm first:border-t-0">
      <Link
        href={`/books/${bookId}/sections/${section.id}`}
        className="font-medium hover:underline"
      >
        {section.display_title}
      </Link>
      {section.location_label ? (
        <span className="text-muted-foreground text-xs">{section.location_label}</span>
      ) : null}
      <span className="text-muted-foreground text-xs tabular-nums">
        {section.char_count.toLocaleString()} chars
      </span>
      {section.structure_confidence !== "high" ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <Badge variant="outline">{section.structure_confidence} confidence</Badge>
          </TooltipTrigger>
          <TooltipContent>
            The document says this boundary came from: {section.structure_source.replace(/_/g, " ")}
            .
          </TooltipContent>
        </Tooltip>
      ) : null}
      {section.is_unlabelled ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <Badge variant="outline">no heading</Badge>
          </TooltipTrigger>
          <TooltipContent>
            The source printed no heading here, so the unit is labelled by its location.
          </TooltipContent>
        </Tooltip>
      ) : null}
      {section.is_empty ? <Badge variant="destructive">no text</Badge> : null}
    </li>
  );
}

export function BookStructure({
  bookId,
  chapters,
}: {
  bookId: number;
  chapters: readonly ChapterOut[];
}) {
  if (chapters.length === 0) {
    return <p className="text-muted-foreground text-sm">This book has no chapters.</p>;
  }

  return (
    <ol className="space-y-4">
      {chapters.map((chapter) => (
        <li key={chapter.id} className="rounded-lg border">
          <div className="flex flex-wrap items-center gap-2 border-b bg-muted/40 px-3 py-2">
            <span className="font-medium">{chapterLabel(chapter)}</span>
            {chapter.location_label ? (
              <span className="text-muted-foreground text-xs">{chapter.location_label}</span>
            ) : null}
            {chapter.is_unlabelled ? <Badge variant="outline">no heading</Badge> : null}
            <span className="ml-auto text-muted-foreground text-xs">
              {chapter.sections.length} section{chapter.sections.length === 1 ? "" : "s"}
            </span>
          </div>
          {chapter.sections.length > 0 ? (
            <ul className="px-3">
              {chapter.sections.map((section) => (
                <SectionRow key={section.id} bookId={bookId} section={section} />
              ))}
            </ul>
          ) : (
            <p className="px-3 py-2 text-muted-foreground text-sm">
              This chapter declared no sections.
            </p>
          )}
        </li>
      ))}
    </ol>
  );
}
