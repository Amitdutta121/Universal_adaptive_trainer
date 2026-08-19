"use client";

/**
 * One subtopic: what it means, and what it is identified by.
 *
 * A subtopic is the unit a student's weakness is measured on, so the fact this
 * page has to make checkable is that renaming it does not move its stable id.
 *
 * The ADR-021 gate applies more sharply here than anywhere else, and this screen
 * departs from the Jinja page deliberately. `curriculum_subtopic.html` keeps a
 * "Supporting sections" panel for an uploaded taxonomy and fills it with
 * "Uploaded taxonomies do not include textbook evidence". A heading naming a
 * property, above a body denying it, still frames the subtopic as a thing that
 * could have had evidence. So for an upload those cards are absent, and the
 * definition card ends with one plain statement of what it does and does not
 * carry.
 */

import { ArrowLeft, Pencil } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { PageHeader } from "@/components/page-header";
import { QueryError, TableSkeleton } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useCurriculumSubtopic } from "@/lib/api/queries";
import { pluralise } from "@/lib/display";
import {
  ItemRenameDialog,
  type RenameTarget,
} from "../../components/item-rename-dialog";
import {
  CONFIDENCE_VARIANT,
  CURRICULUM_ITEM_STATUS_LABEL,
  stableIdMeaning,
} from "../../curriculum-display";

export function SubtopicDetailScreen({ subtopicId }: { subtopicId: number }) {
  const [renaming, setRenaming] = useState<RenameTarget | null>(null);
  const { data, isPending, isError, error } = useCurriculumSubtopic(subtopicId);

  if (isPending) {
    return (
      <>
        <PageHeader title="Subtopic" />
        <TableSkeleton />
      </>
    );
  }

  if (isError) {
    return (
      <>
        <PageHeader title="Subtopic" />
        <QueryError error={error} />
        <Link href="/curriculum" className="text-muted-foreground text-sm hover:underline">
          ← All curriculum versions
        </Link>
      </>
    );
  }

  const {
    subtopic,
    topic,
    curriculum_version_id,
    is_taxonomy_upload: fromUpload,
    candidate_labels,
    grouping_reason,
    confidence,
    evidence,
    book_count,
  } = data;

  return (
    <>
      <PageHeader
        title={subtopic.name}
        summary={
          fromUpload
            ? topic.name
            : [
                topic.name,
                `${pluralise(evidence.length, "supporting section")} / ${pluralise(book_count, "book")}`,
              ].join(" · ")
        }
        actions={
          <>
            {!fromUpload && confidence ? (
              <Badge variant={CONFIDENCE_VARIANT[confidence]}>{confidence} confidence</Badge>
            ) : null}
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                setRenaming({
                  kind: "subtopic",
                  id: subtopic.id,
                  name: subtopic.name,
                  description: subtopic.description,
                })
              }
            >
              <Pencil />
              Rename
            </Button>
          </>
        }
      />

      <Link
        href={`/curriculum/versions/${curriculum_version_id}`}
        className="flex w-fit items-center gap-1 text-muted-foreground text-sm hover:underline"
      >
        <ArrowLeft className="size-3" />
        Back to the curriculum version
      </Link>

      <Card>
        <CardHeader>
          <CardTitle>Definition</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm">{subtopic.description || "No definition was recorded."}</p>
          <dl className="text-sm">
            <div className="flex flex-wrap justify-between gap-2 border-b py-2">
              <dt className="text-muted-foreground">Topic</dt>
              <dd>
                <Link
                  href={`/curriculum/versions/${curriculum_version_id}`}
                  className="hover:underline"
                >
                  {topic.name}
                </Link>
              </dd>
            </div>
            <div className="flex flex-wrap justify-between gap-2 border-b py-2">
              <dt className="text-muted-foreground">Review status</dt>
              <dd>{CURRICULUM_ITEM_STATUS_LABEL[subtopic.review_status]}</dd>
            </div>
            <div className="flex flex-wrap justify-between gap-2 py-2">
              <dt className="text-muted-foreground">Stable id</dt>
              <dd className="font-mono text-xs">{subtopic.stable_id ?? "—"}</dd>
            </div>
          </dl>
          <p className="text-muted-foreground text-sm">{stableIdMeaning(fromUpload)}</p>
          {fromUpload ? (
            <p className="text-muted-foreground text-sm">
              This subtopic comes from an uploaded taxonomy. It carries no textbook evidence,
              grouping rationale or model metadata, by design.
            </p>
          ) : null}
        </CardContent>
      </Card>

      {/* Legacy proposals only, both of them: an upload has neither. */}
      {!fromUpload ? (
        <Card>
          <CardHeader>
            <CardTitle>Why these were grouped</CardTitle>
            <CardDescription>
              Wordings from the books judged to describe the same skill.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {candidate_labels.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {candidate_labels.map((label) => (
                  <Badge key={label} variant="outline">
                    {label}
                  </Badge>
                ))}
              </div>
            ) : (
              <p className="text-muted-foreground text-sm">No candidate labels were recorded.</p>
            )}
            <p className="text-sm">
              {grouping_reason || "No grouping rationale was recorded."}
            </p>
          </CardContent>
        </Card>
      ) : null}

      {!fromUpload ? (
        <Card>
          <CardHeader>
            <CardTitle>Supporting sections</CardTitle>
          </CardHeader>
          <CardContent>
            {evidence.length > 0 ? (
              <ol className="space-y-4">
                {evidence.map((item) => (
                  <li key={item.id} className="rounded-lg border p-3">
                    <Link
                      href={`/books/${item.book_id}/sections/${item.section_id}`}
                      className="font-medium text-sm hover:underline"
                    >
                      {item.citation}
                    </Link>
                    <p className="mt-1 text-sm">
                      <span className="text-muted-foreground">Called here: </span>
                      {item.candidate_label}
                    </p>
                    {item.definition ? <p className="mt-1 text-sm">{item.definition}</p> : null}
                    {item.quotes.length > 0 ? (
                      <ul className="mt-2 space-y-1">
                        {item.quotes.map((quote) => (
                          <li
                            key={quote}
                            className="border-muted-foreground/30 border-l-2 pl-3 text-muted-foreground text-sm italic"
                          >
                            {quote}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-muted-foreground text-sm">
                No supporting sections were recorded for this subtopic.
              </p>
            )}
          </CardContent>
        </Card>
      ) : null}

      <ItemRenameDialog
        key={`rename-${renaming?.id ?? "none"}`}
        target={renaming}
        open={renaming !== null}
        onOpenChange={(open) => !open && setRenaming(null)}
      />
    </>
  );
}
