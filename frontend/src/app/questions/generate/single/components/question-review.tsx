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
import { Textarea } from "@/components/ui/textarea";
import { useQuestion, useRegenerateWithFeedback, useSubmitReview } from "@/lib/api/queries";
import type { Schemas } from "@/lib/api/types";

export function QuestionReview({
  questionId,
  onGenerateAnother,
  onRegenerated,
}: {
  questionId: number;
  /** Absent in hosts with no chunk to generate from (the question bank). */
  onGenerateAnother?: () => void;
  /** Called with the new question's id after a "Regenerate with feedback". */
  onRegenerated?: (newQuestionId: number) => void;
}) {
  const { data: detail, isPending, isError, error } = useQuestion(questionId);
  const submitReview = useSubmitReview();
  const regenerate = useRegenerateWithFeedback();
  const form = useReviewForm(detail ?? null);
  const [justSaved, setJustSaved] = useState(false);
  const [feedback, setFeedback] = useState("");

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

  async function onRegenerate() {
    if (!feedback.trim() || regenerate.isPending) return;
    try {
      const result = await regenerate.mutateAsync({ questionId, feedback: feedback.trim() });
      toast.success("New question generated");
      setFeedback("");
      onRegenerated?.(result.question_id);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Regeneration failed.";
      toast.error("Regeneration failed", { description: message });
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

      <div className="space-y-3 rounded-[1rem] border p-4">
        <div className="review-eyebrow">Regenerate with feedback</div>
        <p className="text-muted-foreground text-sm">
          Write a new question from the same section, type and difficulty. This does not change or
          review the current question.
        </p>
        <Textarea
          rows={4}
          value={feedback}
          onChange={(event) => setFeedback(event.target.value)}
          disabled={regenerate.isPending}
          placeholder="e.g. The distractors are too obvious — make them plausible misconceptions."
          className="review-textarea"
        />
        <div className="flex items-center gap-3">
          <Button
            onClick={() => void onRegenerate()}
            disabled={!feedback.trim() || regenerate.isPending}
          >
            {regenerate.isPending ? "Regenerating…" : "Regenerate with feedback"}
          </Button>
        </div>
        {regenerate.isError ? <QueryError error={regenerate.error} /> : null}
      </div>

      {justSaved ? (
        <div
          className={`flex items-center rounded-[1rem] border bg-muted/40 p-4 ${
            onGenerateAnother ? "justify-between" : ""
          }`}
        >
          <p className="text-sm">
            Saved — nothing here is overwritten, this is a new review record.
          </p>
          {onGenerateAnother ? (
            <Button onClick={onGenerateAnother}>Generate another from this chunk</Button>
          ) : null}
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
