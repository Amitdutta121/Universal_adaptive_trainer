"use client";

/**
 * The generated question, its judge scores, and the professor's verdict — for
 * exactly one question, outside the Review Queue's "next unreviewed" flow.
 *
 * Deliberately not new: it composes the same pieces the Review Queue already
 * renders a question with, so a question generated here looks and behaves
 * exactly like one reviewed from the queue.
 */

import { useState } from "react";
import { toast } from "sonner";
import { ReviewActionBar } from "@/app/review/components/review-action-bar";
import { JudgeRail, ValidationSummary } from "@/app/review/components/review-feedback";
import {
  ReviewQuestionContent,
  ReviewQuestionSurface,
} from "@/app/review/components/review-question-content";
import { useReviewForm } from "@/app/review/use-review-form";
import { QueryError, TableSkeleton } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { useQuestion, useSubmitReview } from "@/lib/api/queries";
import type { Schemas } from "@/lib/api/types";

export function QuestionReview({
  questionId,
  onGenerateAnother,
}: {
  questionId: number;
  onGenerateAnother: () => void;
}) {
  const { data: detail, isPending, isError, error } = useQuestion(questionId);
  const submitReview = useSubmitReview();
  const form = useReviewForm(detail ?? null);
  const [justSaved, setJustSaved] = useState(false);

  if (isPending) return <TableSkeleton rows={3} />;
  if (isError || !detail) return <QueryError error={error} />;

  const canReject = form.reasons.length > 0;
  const canSubmit =
    form.effectiveDecision === "reject"
      ? canReject
      : form.effectiveDecision === "edit"
        ? form.changedFields.length > 0
        : true;

  async function onSubmit() {
    if (!canSubmit || submitReview.isPending) return;
    const body: Schemas["ReviewRequest"] = {
      decision: form.effectiveDecision,
      ...(form.reasons.length > 0 ? { reasons: form.reasons } : {}),
      ...(form.comment.trim() ? { comment: form.comment } : {}),
      ...(form.effectiveDecision === "edit"
        ? {
            prompt: form.promptEdit,
            reference_solution: form.referenceEdit,
            tests: form.testsEdit,
          }
        : {}),
    };

    try {
      await submitReview.mutateAsync({ questionId, body });
      setJustSaved(true);
      toast.success("Review saved");
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Failed to save review.";
      toast.error("Review not saved", { description: message });
    }
  }

  return (
    <div data-review-theme="signal" className="review-theme-root min-w-0 space-y-4">
      <ReviewQuestionSurface
        detail={detail}
        isInlineEditing={form.isInlineEditing}
        promptEdit={form.promptEdit}
        onPromptEdit={form.setPromptEdit}
      />
      <ReviewQuestionContent
        detail={detail}
        isInlineEditing={form.isInlineEditing}
        promptEdit={form.promptEdit}
        referenceEdit={form.referenceEdit}
        testsEdit={form.testsEdit}
        onPromptEdit={form.setPromptEdit}
        onReferenceEdit={form.setReferenceEdit}
        onTestsEdit={form.setTestsEdit}
      />
      <JudgeRail detail={detail} />
      <ValidationSummary detail={detail} />

      {justSaved ? (
        <div className="flex items-center justify-between rounded-[1rem] border bg-muted/40 p-4">
          <p className="text-sm">
            Saved — nothing here is overwritten, this is a new review record.
          </p>
          <Button onClick={onGenerateAnother}>Generate another from this chunk</Button>
        </div>
      ) : (
        <ReviewActionBar
          detail={detail}
          decision={form.decision}
          effectiveDecision={form.effectiveDecision}
          reasons={form.reasons}
          changedFields={form.changedFields}
          comment={form.comment}
          isSubmitting={submitReview.isPending}
          canSubmit={canSubmit}
          canReject={canReject}
          onDecisionChange={form.setDecision}
          onReasonsChange={form.setReasons}
          onCommentChange={form.setComment}
          onSubmit={() => void onSubmit()}
          onSkip={onGenerateAnother}
        />
      )}
    </div>
  );
}
