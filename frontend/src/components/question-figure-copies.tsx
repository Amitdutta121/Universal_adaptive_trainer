"use client";

import { Loader2 } from "lucide-react";
import { useState } from "react";
import { QuestionBody } from "@/components/question-body";
import { Button } from "@/components/ui/button";
import { useRegenerateFigureCopy } from "@/lib/api/queries";
import type { QuestionFigure as Figure, QuestionDetail } from "@/lib/api/types";

/**
 * A computed-figure question's copies side by side, each with its own key, and the program
 * that drew them (ADR-080). Renders nothing for any other question.
 */
export function QuestionFigureCopies({
  detail,
  onUpdated,
}: {
  detail: QuestionDetail;
  /** Called after a copy is regenerated and the detail query has been invalidated. */
  onUpdated?: () => void;
}) {
  const copies = detail.figure_copies ?? [];
  const regenerate = useRegenerateFigureCopy();
  const [pendingOrdinal, setPendingOrdinal] = useState<number | null>(null);
  const [errorOrdinal, setErrorOrdinal] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (copies.length === 0) return null;

  async function onRegenerate(ordinal: number) {
    setPendingOrdinal(ordinal);
    setErrorOrdinal(null);
    setErrorMessage(null);
    try {
      await regenerate.mutateAsync({ questionId: detail.question.id, ordinal });
      onUpdated?.();
    } catch (caught) {
      setErrorOrdinal(ordinal);
      setErrorMessage(caught instanceof Error ? caught.message : "Failed to regenerate this copy.");
    } finally {
      setPendingOrdinal(null);
    }
  }

  return (
    <section className="space-y-3" aria-label="Copies of this question">
      <div className="font-medium text-sm">
        {copies.length} copies: each student is shown one, and scored against its key
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {copies.map((copy) => (
          <div key={copy.ordinal} className="space-y-2 rounded-md border p-3">
            <div className="flex items-center justify-between gap-2">
              <div className="text-muted-foreground text-xs">
                Copy {copy.ordinal + 1} (seed {copy.seed})
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={pendingOrdinal !== null}
                onClick={() => void onRegenerate(copy.ordinal)}
              >
                {pendingOrdinal === copy.ordinal ? (
                  <>
                    <Loader2 className="size-3.5 animate-spin" />
                    Regenerating…
                  </>
                ) : (
                  "Regenerate"
                )}
              </Button>
            </div>
            <QuestionBody
              prompt={copy.prompt}
              figure={(copy.content.figure as Figure | undefined) ?? null}
              promptClassName="text-[13px]"
            />
            {copy.reference_solution ? (
              <div className="text-xs">
                <span className="font-medium">Key:</span> {copy.reference_solution}
              </div>
            ) : null}
            {errorOrdinal === copy.ordinal && errorMessage ? (
              <p className="text-destructive text-xs" role="alert">
                {errorMessage}
              </p>
            ) : null}
          </div>
        ))}
      </div>
      {detail.figure_program ? (
        <details className="text-xs">
          <summary className="cursor-pointer font-medium">Program that drew the copies</summary>
          <pre className="mt-2 max-h-96 overflow-auto rounded-md bg-muted p-3">
            {detail.figure_program}
          </pre>
        </details>
      ) : null}
    </section>
  );
}
