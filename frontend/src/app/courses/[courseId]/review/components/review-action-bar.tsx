"use client";

import { ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DECISIONS, type ReviewDecision } from "../review-types";

type ReviewActionBarProps = {
  decision: ReviewDecision;
  effectiveDecision: ReviewDecision;
  changedFields: string[];
  comment: string;
  isSubmitting: boolean;
  canSubmit: boolean;
  onDecisionChange: (decision: ReviewDecision) => void;
  onCommentChange: (value: string) => void;
  onSubmit: () => void;
  onSkip?: () => void;
};

/**
 * Verdict controls for a single generated question (outside the review queue).
 * Reject takes an optional one-line comment. Edit stays a peer action.
 */
export function ReviewActionBar({
  decision,
  effectiveDecision,
  changedFields,
  comment,
  isSubmitting,
  canSubmit,
  onDecisionChange,
  onCommentChange,
  onSubmit,
  onSkip,
}: ReviewActionBarProps) {
  const submitLabel = isSubmitting
    ? "Saving..."
    : effectiveDecision === "reject"
      ? "Reject and continue"
      : effectiveDecision === "edit"
        ? "Save and approve"
        : "Approve and continue";

  return (
    <div className="review-sticky rounded-[1rem] border px-5 py-4">
      <div className="space-y-3">
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
            <span>changed_fields: {changedFields.join(", ") || "none"}</span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {effectiveDecision === "reject" || effectiveDecision === "edit" ? (
            <Input
              value={comment}
              onChange={(event) => onCommentChange(event.target.value)}
              placeholder={
                effectiveDecision === "reject"
                  ? "Why reject? (optional)"
                  : "What did you change? (optional)"
              }
              aria-label="Comment"
              className="h-9 min-w-56 flex-1"
            />
          ) : (
            <div className="flex-1" />
          )}

          <Button onClick={onSubmit} disabled={!canSubmit || isSubmitting}>
            {submitLabel}
            <span className="review-kbd">Enter</span>
          </Button>
          {onSkip ? (
            <Button variant="outline" onClick={onSkip} disabled={isSubmitting}>
              Skip
              <ChevronRight className="size-4" />
            </Button>
          ) : null}
        </div>
        {effectiveDecision === "edit" && !canSubmit ? (
          <p className="text-[var(--review-muted)] text-xs">
            Change the prompt, solution or tests above to save an edit.
          </p>
        ) : null}
      </div>
    </div>
  );
}
