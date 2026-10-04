"use client";

import { ChevronDown, ChevronRight, Pencil } from "lucide-react";
import { Fragment } from "react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  DIFFICULTIES,
  DIFFICULTY_LABEL,
  type Difficulty,
  type ReviewDecision,
  type SubtopicOption,
} from "../review-types";

/** Easy / Medium / Hard as one segmented control. */
function DifficultyControl({
  value,
  onChange,
}: {
  value: Difficulty;
  onChange: (value: Difficulty) => void;
}) {
  return (
    <div
      role="radiogroup"
      aria-label="Difficulty"
      className="inline-flex rounded-lg border border-[var(--review-border)] p-0.5"
    >
      {DIFFICULTIES.map((option) => {
        const active = option === value;
        return (
          // biome-ignore lint/a11y/useSemanticElements: a segmented control, not a native radio list
          <button
            key={option}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(option)}
            className={cn(
              "h-7 rounded-md px-3 text-sm transition-colors",
              active
                ? "bg-[var(--review-accent)] text-[var(--primary-foreground)]"
                : "text-[var(--review-foreground-2)] hover:bg-[var(--review-accent-soft)]",
            )}
          >
            {DIFFICULTY_LABEL[option]}
          </button>
        );
      })}
    </div>
  );
}

/** The approved taxonomy's subtopics, grouped by topic, as a checklist menu. */
function SubtopicPicker({
  options,
  value,
  onChange,
}: {
  options: readonly SubtopicOption[];
  value: readonly number[];
  onChange: (value: number[]) => void;
}) {
  const names = new Map(options.map((option) => [option.id, option.name]));
  const chosen = value.map((id) => names.get(id) ?? `#${id}`);
  const topics = [...new Set(options.map((option) => option.topicName))];
  const toggle = (id: number, on: boolean) =>
    onChange(on ? [...value, id] : value.filter((each) => each !== id));

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          aria-label="Subtopics"
          className="max-w-[22rem] justify-between font-normal"
          disabled={options.length === 0}
        >
          <span className="truncate">
            {chosen.length === 0 ? (
              <span className="text-muted-foreground">
                {options.length === 0 ? "No approved taxonomy" : "Choose subtopics"}
              </span>
            ) : (
              <>
                {chosen[0]}
                {chosen.length > 1 ? (
                  <span className="text-muted-foreground"> +{chosen.length - 1}</span>
                ) : null}
              </>
            )}
          </span>
          <ChevronDown className="size-4 text-muted-foreground" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-h-80 min-w-64 overflow-y-auto">
        {topics.map((topic, index) => (
          <Fragment key={topic}>
            {index > 0 ? <DropdownMenuSeparator /> : null}
            <DropdownMenuLabel className="text-muted-foreground text-xs">{topic}</DropdownMenuLabel>
            {options
              .filter((option) => option.topicName === topic)
              .map((option) => (
                <DropdownMenuCheckboxItem
                  key={option.id}
                  checked={value.includes(option.id)}
                  onCheckedChange={(on) => toggle(option.id, on)}
                  onSelect={(event) => event.preventDefault()}
                >
                  {option.name}
                </DropdownMenuCheckboxItem>
              ))}
          </Fragment>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

type ReviewVerdictBarProps = {
  decision: ReviewDecision;
  effectiveDecision: ReviewDecision;
  difficulty: Difficulty;
  subtopicIds: number[];
  subtopicOptions: readonly SubtopicOption[];
  difficultyConfirmed: boolean;
  subtopicsConfirmed: boolean;
  onConfirmDifficulty: () => void;
  onConfirmSubtopics: () => void;
  comment: string;
  isSubmitting: boolean;
  canSubmit: boolean;
  onDecisionChange: (decision: ReviewDecision) => void;
  onDifficultyChange: (value: Difficulty) => void;
  onSubtopicsChange: (value: number[]) => void;
  onCommentChange: (value: string) => void;
  onSubmit: () => void;
  onSkip?: () => void;
};

/**
 * The professor's verdict on one question: confirm or correct its difficulty and subtopics,
 * then accept or reject it (reject takes an optional one-line comment). Editing the question
 * itself stays available as a secondary action.
 */
export function ReviewVerdictBar({
  decision,
  effectiveDecision,
  difficulty,
  subtopicIds,
  subtopicOptions,
  difficultyConfirmed,
  subtopicsConfirmed,
  onConfirmDifficulty,
  onConfirmSubtopics,
  comment,
  isSubmitting,
  canSubmit,
  onDecisionChange,
  onDifficultyChange,
  onSubtopicsChange,
  onCommentChange,
  onSubmit,
  onSkip,
}: ReviewVerdictBarProps) {
  const submitLabel = isSubmitting
    ? "Saving..."
    : effectiveDecision === "reject"
      ? "Reject and continue"
      : effectiveDecision === "edit"
        ? "Save edit and accept"
        : "Accept and continue";

  return (
    <div className="review-sticky rounded-[1rem] border px-5 py-4">
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
          <div className="flex items-center gap-2">
            <span className="review-eyebrow">Difficulty</span>
            <DifficultyControl value={difficulty} onChange={onDifficultyChange} />
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={difficultyConfirmed}
              onClick={onConfirmDifficulty}
            >
              {difficultyConfirmed ? "Difficulty confirmed" : "Confirm difficulty"}
            </Button>
          </div>
          <div className="flex min-w-0 items-center gap-2">
            <span className="review-eyebrow">Topic</span>
            <SubtopicPicker
              options={subtopicOptions}
              value={subtopicIds}
              onChange={onSubtopicsChange}
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={subtopicsConfirmed || subtopicIds.length === 0}
              onClick={onConfirmSubtopics}
            >
              {subtopicsConfirmed ? "Subtopics confirmed" : "Confirm subtopics"}
            </Button>
          </div>
        </div>

        {!difficultyConfirmed || !subtopicsConfirmed ? (
          <p className="text-[var(--review-muted)] text-xs">
            Confirm or correct the difficulty and subtopics before submitting.
          </p>
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant={decision === "approve" ? "default" : "outline"}
            aria-pressed={decision === "approve"}
            className={decision === "approve" ? "bg-[var(--review-ok)] text-white" : ""}
            onClick={() => onDecisionChange("approve")}
          >
            Accept
          </Button>
          <Button
            type="button"
            variant={decision === "reject" ? "default" : "outline"}
            aria-pressed={decision === "reject"}
            className={decision === "reject" ? "bg-[var(--review-critical)] text-white" : ""}
            onClick={() => onDecisionChange("reject")}
          >
            Reject
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-pressed={decision === "edit"}
            className={decision === "edit" ? "text-[var(--review-accent)]" : ""}
            onClick={() => onDecisionChange(decision === "edit" ? "approve" : "edit")}
          >
            <Pencil className="size-3.5" />
            {decision === "edit" ? "Stop editing" : "Edit question"}
          </Button>

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
