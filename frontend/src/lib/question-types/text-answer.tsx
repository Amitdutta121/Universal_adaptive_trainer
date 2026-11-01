"use client";

/**
 * The free-text answer box, shared by output prediction and the three code-writing types,
 * and the fallback for a question whose type has no built UI.
 */

import { Textarea } from "@/components/ui/textarea";
import type { AnswerInputProps } from "./registry";

export function TextAnswerInput({
  question,
  value,
  onChange,
  onSubmit,
  label,
  rows,
  placeholder,
}: AnswerInputProps & { label: string; rows: number; placeholder: string }) {
  return (
    <div className="space-y-2">
      <label
        className="font-medium text-foreground text-sm"
        htmlFor={`answer-${question.attempt_id}`}
      >
        {label}
      </label>
      <Textarea
        id={`answer-${question.attempt_id}`}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
            event.preventDefault();
            onSubmit?.();
          }
        }}
        rows={rows}
        className="rounded-[1.2rem] border-border/80 bg-card/85 px-4 py-3 text-sm leading-7 shadow-[0_18px_40px_-34px_rgb(19_26_28_/_0.32)]"
        placeholder={placeholder}
      />
      <p className="text-muted-foreground text-xs">
        Tip: press Ctrl+Enter (⌘+Enter on Mac) to submit without leaving the keyboard.
      </p>
    </div>
  );
}

export const CODE_ANSWER_LABEL = "Your Python";

/** The code-writing box: code_completion, debugging, coding, and any type with no built UI. */
export function CodeAnswerInput(props: AnswerInputProps) {
  return (
    <TextAnswerInput
      {...props}
      label={CODE_ANSWER_LABEL}
      rows={14}
      placeholder="Write your answer here"
    />
  );
}

/** Executable types show no type-specific key; the reference solution block covers them. */
export function NoReviewContent() {
  return null;
}
