"use client";

import { ExternalLink } from "lucide-react";
import Link from "next/link";
import { parseAsInteger, parseAsStringLiteral, useQueryState } from "nuqs";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { EmptyState, QueryError, TableSkeleton } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useReviewQueue, useSubmitReview } from "@/lib/api/queries";
import type { Schemas } from "@/lib/api/types";
import { ReviewActionBar } from "./components/review-action-bar";
import { JudgeRail, ValidationSummary } from "./components/review-feedback";
import { ReviewQuestionContent, ReviewQuestionSurface } from "./components/review-question-content";
import {
  REVIEW_MODES,
  REVIEW_THEMES,
  type ReviewQueueMode,
  type ReviewTheme,
} from "./review-types";
import { useReviewForm } from "./use-review-form";

export function ReviewScreen() {
  const [mode, setMode] = useQueryState(
    "mode",
    parseAsStringLiteral(REVIEW_MODES).withDefault("all"),
  );
  const [after, setAfter] = useQueryState("after", parseAsInteger);
  const [theme, setTheme] = useQueryState(
    "theme",
    parseAsStringLiteral(REVIEW_THEMES).withDefault("signal"),
  );
  const { data, isPending, isError, error } = useReviewQueue({ mode, after });
  const submitReview = useSubmitReview();

  const detail = data?.question ?? null;
  const form = useReviewForm(detail);
  const canReject = form.reasons.length > 0;
  const canSubmit =
    form.effectiveDecision === "reject"
      ? canReject
      : form.effectiveDecision === "edit"
        ? form.changedFields.length > 0
        : true;

  async function onSubmit() {
    if (!detail || !canSubmit || submitReview.isPending) return;
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
      const review = await submitReview.mutateAsync({
        questionId: detail.question.id,
        body,
      });

      const outcome = review.outcome;
      if (!outcome) {
        toast.info("Review saved", {
          description: "Saved, but there was no completed judge outcome to compare against.",
        });
      } else {
        const destructive = outcome.cell === "missed" || outcome.cell === "confirmed_bad";
        const description = [
          outcome.action,
          outcome.attributed_labels.length > 0
            ? `Judges named at fault: ${outcome.attributed_labels.join(", ")}.`
            : "",
          outcome.refresh_error ?? "",
        ]
          .filter(Boolean)
          .join(" ");

        if (destructive) {
          toast.error(outcome.cell.replace(/_/g, " "), { description });
        } else {
          toast.success(outcome.cell.replace(/_/g, " "), { description });
        }
      }

      await setAfter(detail.question.id);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Failed to save review.";
      toast.error("Review not saved", { description: message });
    }
  }

  return (
    <div data-review-theme={theme} className="review-theme-root flex min-w-0 flex-col gap-6">
      <div className="review-header-sticky sticky top-0 z-30 -mx-6 px-6 pt-1 pb-4">
        <PageHeader
          title="Review Queue"
          summary="Professor feedback lives here now. Review the student-facing surface first, then decide."
          actions={
            <>
              <Select
                value={mode}
                onValueChange={(value) => void setMode(value as ReviewQueueMode)}
              >
                <SelectTrigger className="review-select-trigger w-40" size="sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="scoreable">Judged only</SelectItem>
                </SelectContent>
              </Select>
              <Select value={theme} onValueChange={(value) => void setTheme(value as ReviewTheme)}>
                <SelectTrigger className="review-select-trigger w-36" size="sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="signal">Signal</SelectItem>
                  <SelectItem value="carbon">Carbon</SelectItem>
                </SelectContent>
              </Select>
            </>
          }
        />
      </div>

      {isError ? <QueryError error={error} /> : null}
      {isPending ? <TableSkeleton rows={6} /> : null}

      {data ? (
          <Card className="review-panel border">
            <CardHeader>
              <div className="review-eyebrow">Queue</div>
              <CardTitle>Professor feedback progress</CardTitle>
            <CardDescription className="flex flex-wrap items-center gap-2">
              <span>
                <strong>{data.reviewed}</strong> of {data.total} reviewed
              </span>
              <span>-</span>
              <span>{data.remaining} left</span>
              {data.mode === "scoreable" ? (
                <span>- {data.scoreable_remaining} scoreable left</span>
              ) : null}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Progress
              value={data.total ? (data.reviewed / data.total) * 100 : 0}
              className="review-progress"
            />
          </CardContent>
        </Card>
      ) : null}
      {data && !detail ? (
        data.remaining === 0 ? (
          <EmptyState
            title="Nothing left to review"
            hint="Every question in the bank has a verdict."
          />
        ) : (
          <Card className="review-panel border">
            <CardHeader>
              <CardTitle>End of this pass</CardTitle>
              <CardDescription>
                No further match after this point. Restart from the first unreviewed question.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button onClick={() => void setAfter(null)}>Start again</Button>
            </CardContent>
          </Card>
        )
      ) : null}

      {detail ? (
        <>
          <div className="grid min-w-0 gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
            <div className="min-w-0 space-y-4">
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
              <ValidationSummary detail={detail} />
            </div>

            <div className="min-w-0 space-y-4">
              <JudgeRail detail={detail} />
              <Card className="review-panel border">
                <CardHeader>
                  <div className="review-eyebrow">Context</div>
                  <CardTitle>Question detail</CardTitle>
                  <CardDescription>
                    Open the full detail page without leaving the bank permanently.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Button asChild variant="outline" className="w-full justify-between">
                    <Link href={`/questions/${detail.question.id}`}>
                      Open detail page
                      <ExternalLink className="size-4" />
                    </Link>
                  </Button>
                </CardContent>
              </Card>
            </div>
          </div>

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
            onSubmit={onSubmit}
            onSkip={() => void setAfter(detail.question.id)}
          />
        </>
      ) : null}
    </div>
  );
}
