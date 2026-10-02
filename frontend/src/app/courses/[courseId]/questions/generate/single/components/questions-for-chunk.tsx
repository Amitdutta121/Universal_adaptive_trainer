"use client";

/**
 * Every question already generated from the chunk currently in view.
 *
 * Sits underneath the PDF pane rather than beside it, because it answers a
 * question about *that* chunk specifically ("what has this one already
 * produced?"), not about the run being configured on the right. Picking one
 * hands its id up to the parent, which reuses the same `QuestionReview` a
 * freshly generated question renders in — a question opened from here looks
 * and behaves exactly like one just generated.
 */

import { QueryError } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useQuestionsForSection } from "@/lib/api/queries";
import { QUESTION_TYPE_SHORT } from "../../spec-sheet-types";

const STATUS_LABEL: Record<string, string> = {
  generated: "Generated",
  validation_passed: "Validated",
  validation_failed: "Failed validation",
  approved: "Approved",
  rejected: "Rejected",
};

export function QuestionsForChunk({
  sectionId,
  openQuestionId,
  onOpen,
}: {
  sectionId: number | null;
  openQuestionId: number | null;
  onOpen: (questionId: number) => void;
}) {
  const { data, isPending, isError, error } = useQuestionsForSection(sectionId);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-[1rem] border">
      <div className="flex items-center justify-between border-b bg-muted/40 px-3 py-2.5">
        <span className="font-mono text-[0.67rem] text-muted-foreground uppercase tracking-[0.16em]">
          Questions from this chunk
        </span>
        {data ? (
          <span className="font-mono text-[0.67rem] text-muted-foreground">
            {data.questions.length}
          </span>
        ) : null}
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {sectionId === null ? (
          <p className="p-3 text-muted-foreground text-sm">
            Scroll or pick a chunk to see what it has already produced.
          </p>
        ) : isError ? (
          <div className="p-2">
            <QueryError error={error} />
          </div>
        ) : isPending ? (
          <div className="space-y-2 p-1">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : data.questions.length === 0 ? (
          <p className="p-3 text-muted-foreground text-sm">
            No questions generated from this chunk yet.
          </p>
        ) : (
          <ul className="space-y-1.5">
            {data.questions.map((question) => (
              <li key={question.id}>
                <button
                  type="button"
                  onClick={() => onOpen(question.id)}
                  className={`w-full rounded-md border p-2.5 text-left ${
                    question.id === openQuestionId
                      ? "border-primary bg-primary/10"
                      : "hover:bg-muted/50"
                  }`}
                >
                  <p className="line-clamp-2 text-[0.8rem] leading-5">{question.prompt}</p>
                  <div className="mt-1.5 flex flex-wrap items-center gap-1">
                    <Badge variant="outline" className="font-mono text-[0.6rem]">
                      {question.question_type
                        ? QUESTION_TYPE_SHORT[question.question_type]
                        : question.kind}
                    </Badge>
                    <Badge variant="outline" className="font-mono text-[0.6rem] capitalize">
                      {question.difficulty}
                    </Badge>
                    <Badge
                      variant={question.status === "rejected" ? "destructive" : "secondary"}
                      className="font-mono text-[0.6rem]"
                    >
                      {STATUS_LABEL[question.status] ?? question.status}
                    </Badge>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
