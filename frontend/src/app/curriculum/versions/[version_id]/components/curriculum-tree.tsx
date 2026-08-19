"use client";

/**
 * The Topic → Subtopic tree, exactly as the document declared it.
 *
 * Client only because each row offers a rename; without that this would be a
 * server component like `books/[book_id]/components/book-structure.tsx`, since it
 * holds no state and formats no timestamp.
 *
 * What it deliberately does not show for an uploaded taxonomy: per-subtopic
 * evidence counts, book counts and confidence. An upload carries none of those
 * (ADR-021), and `SubtopicSummary` does not even model them — so the omission is
 * enforced by the type rather than by discipline.
 *
 * A review status is badged only when it is not `accepted`. Every row of an
 * uploaded taxonomy is accepted, so an always-on badge would be a column of
 * identical pills teaching the professor to ignore all of them.
 */

import { Pencil } from "lucide-react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { SubtopicSummary, TopicOut } from "@/lib/api/types";
import { pluralise } from "@/lib/display";
import {
  CURRICULUM_ITEM_STATUS_LABEL,
  CURRICULUM_ITEM_STATUS_VARIANT,
} from "../../../curriculum-display";
import type { RenameTarget } from "../../../components/item-rename-dialog";

function StableId({ id }: { id: string | null }) {
  // A legacy row may carry none. Never render the string "null".
  if (!id) return null;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge variant="outline" className="font-mono text-[11px]">
          {id}
        </Badge>
      </TooltipTrigger>
      <TooltipContent>Stable identifier — it survives display-name edits.</TooltipContent>
    </Tooltip>
  );
}

function ItemStatus({ status }: { status: SubtopicSummary["review_status"] }) {
  if (status === "accepted") return null;
  return (
    <Badge variant={CURRICULUM_ITEM_STATUS_VARIANT[status]}>
      {CURRICULUM_ITEM_STATUS_LABEL[status]}
    </Badge>
  );
}

function SubtopicRow({
  subtopic,
  onRename,
}: {
  subtopic: SubtopicSummary;
  onRename: (target: RenameTarget) => void;
}) {
  return (
    <li className="border-t py-2 text-sm first:border-t-0">
      <div className="flex flex-wrap items-center gap-2">
        <Link
          href={`/curriculum/subtopics/${subtopic.id}`}
          className="font-medium hover:underline"
        >
          {subtopic.name}
        </Link>
        <StableId id={subtopic.stable_id} />
        <ItemStatus status={subtopic.review_status} />
        <Button
          variant="ghost"
          size="icon-sm"
          className="ml-auto"
          aria-label={`Rename ${subtopic.name}`}
          onClick={() =>
            onRename({
              kind: "subtopic",
              id: subtopic.id,
              name: subtopic.name,
              description: subtopic.description,
            })
          }
        >
          <Pencil />
        </Button>
      </div>
      {subtopic.description ? (
        <p className="mt-0.5 text-muted-foreground text-xs">{subtopic.description}</p>
      ) : null}
    </li>
  );
}

export function CurriculumTree({
  topics,
  onRename,
}: {
  topics: readonly TopicOut[];
  onRename: (target: RenameTarget) => void;
}) {
  if (topics.length === 0) {
    return <p className="text-muted-foreground text-sm">This version contains no topics.</p>;
  }

  return (
    <ol className="space-y-4">
      {topics.map((topic) => (
        <li key={topic.id} className="rounded-lg border">
          <div className="border-b bg-muted/40 px-3 py-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{topic.name}</span>
              <StableId id={topic.stable_id} />
              <ItemStatus status={topic.review_status} />
              <span className="ml-auto text-muted-foreground text-xs">
                {pluralise(topic.subtopics.length, "subtopic")}
              </span>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={`Rename ${topic.name}`}
                onClick={() =>
                  onRename({
                    kind: "topic",
                    id: topic.id,
                    name: topic.name,
                    description: topic.description,
                  })
                }
              >
                <Pencil />
              </Button>
            </div>
            {topic.description ? (
              <p className="mt-0.5 text-muted-foreground text-xs">{topic.description}</p>
            ) : null}
          </div>
          {topic.subtopics.length > 0 ? (
            <ul className="px-3">
              {topic.subtopics.map((subtopic) => (
                <SubtopicRow key={subtopic.id} subtopic={subtopic} onRename={onRename} />
              ))}
            </ul>
          ) : (
            <p className="px-3 py-2 text-muted-foreground text-sm">
              This topic declared no subtopics.
            </p>
          )}
        </li>
      ))}
    </ol>
  );
}
