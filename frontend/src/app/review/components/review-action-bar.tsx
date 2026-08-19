"use client";

import { ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import {
  DECISIONS,
  type QuestionDetail,
  REASON_LABEL,
  type RejectionReason,
  type ReviewDecision,
} from "../review-types";
import { reviewReasonOptions } from "../review-utils";

type ReviewActionBarProps = {
  detail: QuestionDetail;
  decision: ReviewDecision;
  effectiveDecision: ReviewDecision;
  reasons: RejectionReason[];
  changedFields: string[];
  comment: string;
  isSubmitting: boolean;
  canSubmit: boolean;
  canReject: boolean;
  onDecisionChange: (decision: ReviewDecision) => void;
  onReasonsChange: (reasons: RejectionReason[]) => void;
  onCommentChange: (value: string) => void;
  onSubmit: () => void;
  onSkip: () => void;
};

export function ReviewActionBar({
  detail,
  decision,
  effectiveDecision,
  reasons,
  changedFields,
  comment,
  isSubmitting,
  canSubmit,
  canReject,
  onDecisionChange,
  onReasonsChange,
  onCommentChange,
  onSubmit,
  onSkip,
}: ReviewActionBarProps) {
  return (
    <div className="rounded-[1rem] border px-5 py-4 review-sticky">
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          {DECISIONS.map((value) => {
            const active = decision === value;
            return (
              <Button
                key={value}
                type="button"
                variant={active ? "default" : "outline"}
                className={[
                  active && value === "approve" ? "bg-[var(--review-ok)] text-white" : "",
                  active && value === "reject" ? "bg-[var(--review-critical)] text-white" : "",
                  active && value === "edit"
                    ? "bg-[var(--review-accent)] text-[var(--primary-foreground)]"
                    : "",
                ].join(" ")}
                onClick={() => onDecisionChange(value)}
              >
                {value === "approve" ? "Approve" : value === "reject" ? "Reject" : "Edit"}
              </Button>
            );
          })}
          <div className="ml-auto flex flex-wrap items-center gap-2 text-[var(--review-muted)] text-xs">
            <span>decision: {effectiveDecision}</span>
            <span>-</span>
            <span>reasons: {reasons.length}</span>
            <span>-</span>
            <span>changed_fields: {changedFields.join(", ") || "none"}</span>
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <Card className="review-panel border">
            <CardHeader>
              <div className="review-eyebrow">Reasons</div>
              <CardTitle>Why are you rejecting?</CardTitle>
              <CardDescription>Required to reject, optional to edit.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-2 sm:grid-cols-2">
              {reviewReasonOptions(detail.question.question_type).map((reason) => {
                const checked = reasons.includes(reason);
                return (
                  <label key={reason} className="review-reason-option" data-checked={checked}>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(event) =>
                        onReasonsChange(
                          event.target.checked
                            ? [...reasons, reason]
                            : reasons.filter((item) => item !== reason),
                        )
                      }
                    />
                    <span className="text-sm">{REASON_LABEL[reason]}</span>
                  </label>
                );
              })}
            </CardContent>
          </Card>

          <Card className="review-panel border">
            <CardHeader>
              <div className="review-eyebrow">Comment</div>
              <CardTitle>What should change?</CardTitle>
              <CardDescription>
                Quoted back to the learners later; say what should change.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Textarea
                rows={5}
                value={comment}
                onChange={(event) => onCommentChange(event.target.value)}
                placeholder="Say what is wrong or what should be better."
                className="review-textarea"
              />
            </CardContent>
          </Card>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={onSubmit} disabled={!canSubmit || isSubmitting}>
            {isSubmitting
              ? "Saving..."
              : effectiveDecision === "reject"
                ? "Reject and continue"
                : effectiveDecision === "edit"
                  ? "Save and approve"
                  : "Approve and continue"}
            <span className="review-kbd">Enter</span>
          </Button>
          <Button variant="outline" onClick={onSkip} disabled={isSubmitting}>
            Skip
            <ChevronRight className="size-4" />
          </Button>
          {effectiveDecision === "reject" && !canReject ? (
            <span className="text-[var(--review-muted)] text-xs">
              Reject stays disabled until you choose at least one reason.
            </span>
          ) : null}
        </div>
      </div>
    </div>
  );
}
