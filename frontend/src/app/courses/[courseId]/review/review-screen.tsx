"use client";

import { AlertCircle, ExternalLink, Loader2 } from "lucide-react";
import { parseAsInteger, parseAsStringLiteral, useQueryState } from "nuqs";
import { useMemo } from "react";
import { toast } from "sonner";
import { CourseLink } from "@/components/course-link";
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
import { useApprovedCurriculum, useReviewQueue, useSubmitReview } from "@/lib/api/queries";
import type { Schemas } from "@/lib/api/types";
import { JudgeRail, ValidationSummary } from "./components/review-feedback";
import { ReviewQuestionContent, ReviewQuestionSurface } from "./components/review-question-content";
import { ReviewVerdictBar } from "./components/review-verdict-bar";
import { NextRoundButton, RoundProgressStrip } from "./components/round-progress";
import {
  REVIEW_MODES,
  REVIEW_THEMES,
  type ReviewQueueMode,
  type ReviewTheme,
  type SubtopicOption,
} from "./review-types";
import { useNextRound } from "./use-next-round";
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
  // Only the questions of the taxonomy chosen in the header are offered.
  const selectedTaxonomy = useApprovedCurriculum();
  const curriculumVersionId = selectedTaxonomy.data?.version.id ?? null;
  const { data, isPending, isError, error } = useReviewQueue({
    mode,
    after,
    curriculumVersionId,
  });
  const submitReview = useSubmitReview();
  const nextRound = useNextRound(curriculumVersionId);

  const subtopicOptions = useMemo<SubtopicOption[]>(
    () =>
      (selectedTaxonomy.data?.topics ?? []).flatMap((topic) =>
        topic.subtopics.map((subtopic) => ({
          id: subtopic.id,
          name: subtopic.name,
          topicName: topic.name,
        })),
      ),
    [selectedTaxonomy.data],
  );
  const subtopicNames = useMemo(
    () => new Map(subtopicOptions.map((option) => [option.id, option.name])),
    [subtopicOptions],
  );

  const detail = data?.question ?? null;
  const form = useReviewForm(detail);
  // Reject needs no reason any more; an edit needs an actual change.
  const canSubmit =
    form.difficultyConfirmed &&
    form.subtopicsConfirmed &&
    form.subtopicIds.length > 0 &&
    (form.effectiveDecision !== "edit" || form.changedFields.length > 0);

  async function onSubmit() {
    if (!detail || !canSubmit || submitReview.isPending) return;
    const body: Schemas["ReviewRequest"] = {
      decision: form.effectiveDecision,
      ...(form.comment.trim() ? { comment: form.comment.trim() } : {}),
      // The final values, always; the backend compares them with the judges' answers.
      corrected_difficulty: form.difficulty,
      corrected_subtopic_ids: form.subtopicIds.length > 0 ? form.subtopicIds : null,
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
        // `action` says the lesson is learned next round; nothing was relearned yet (ADR-063).
        const description = [
          outcome.action,
          outcome.attributed_labels.length > 0
            ? `Judges named at fault: ${outcome.attributed_labels.join(", ")}.`
            : "",
        ]
          .filter(Boolean)
          .join(" ");

        if (destructive) {
          toast.error(outcome.cell.replace(/_/g, " "), { description });
        } else {
          toast.success(outcome.cell.replace(/_/g, " "), { description });
        }
      }

      if (!detail.question.audit) {
        await setAfter(detail.question.id);
      }
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
              <NextRoundButton
                canStart={nextRound.canStart}
                isStarting={nextRound.isStarting}
                disabledReason={nextRound.disabledReason}
                onStart={() => void nextRound.startNext()}
              />
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
        {nextRound.roundId != null ? (
          <div className="mt-3">
            <RoundProgressStrip
              roundId={nextRound.roundId}
              round={nextRound.round}
              error={nextRound.roundError}
              onDismiss={nextRound.dismiss}
            />
          </div>
        ) : null}
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
        nextRound.isGenerating ? (
          <Card className="review-panel border" data-testid="next-question-generating">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Loader2 className="size-4 animate-spin" />
                Generating the next question
              </CardTitle>
              <CardDescription>
                It appears here as soon as it is generated and judged; the rest of the round keeps
                generating while you review.
              </CardDescription>
            </CardHeader>
          </Card>
        ) : data.remaining === 0 ? (
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
          {detail.question.audit ? (
            <div className="review-banner" data-tone="warn" data-testid="audit-banner">
              <AlertCircle className="mt-0.5 size-4 shrink-0 text-[var(--review-critical)]" />
              <div>
                <div className="review-banner-title">A judge rejected this — do you agree?</div>
                <p className="review-banner-copy">
                  {detail.question.audit_metric === "topic" ? "Topic" : "Difficulty"} judge
                  {detail.question.audit_reason
                    ? `: ${detail.question.audit_reason}`
                    : " flagged this draft."}
                </p>
              </div>
            </div>
          ) : null}
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
              <JudgeRail detail={detail} subtopicNames={subtopicNames} />
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
                    <CourseLink href={`/questions/${detail.question.id}`}>
                      Open detail page
                      <ExternalLink className="size-4" />
                    </CourseLink>
                  </Button>
                </CardContent>
              </Card>
            </div>
          </div>

          <ReviewVerdictBar
            decision={form.decision}
            effectiveDecision={form.effectiveDecision}
            difficulty={form.difficulty}
            subtopicIds={form.subtopicIds}
            subtopicOptions={subtopicOptions}
            difficultyConfirmed={form.difficultyConfirmed}
            subtopicsConfirmed={form.subtopicsConfirmed}
            onConfirmDifficulty={form.confirmDifficulty}
            onConfirmSubtopics={form.confirmSubtopics}
            comment={form.comment}
            isSubmitting={submitReview.isPending}
            canSubmit={canSubmit}
            onDecisionChange={form.setDecision}
            onDifficultyChange={form.setDifficulty}
            onSubtopicsChange={form.setSubtopicIds}
            onCommentChange={form.setComment}
            onSubmit={onSubmit}
            onSkip={() => void setAfter(detail.question.id)}
            audit={detail.question.audit}
          />
        </>
      ) : null}
    </div>
  );
}
