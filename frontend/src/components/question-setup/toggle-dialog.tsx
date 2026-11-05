"use client";

/**
 * Asked only when a switch would touch questions that already exist (ADR-070): turning a style
 * or a whole question type off when approved questions use it, or back on when some of them are
 * hidden. Hidden is its own question status: kept in the bank, not served, never a reject.
 * Used by the question setup dialog and by course Settings; design from
 * `app/experiments/question-types/toggle-dialog.tsx`.
 */

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

export interface PendingToggle {
  mode: "off" | "on";
  /** What is being switched: a style or a question type name. */
  label: string;
  /** "the whole course" or a subtopic name. */
  scopeLabel: string;
  /** Approved questions in scope (off) or hidden questions in scope (on). */
  count: number;
  /** Subtopic-difficulty levels that drop below target if they are hidden. */
  slotsBelowTarget: number;
}

export function ToggleDialog({
  pending,
  onCancel,
  onConfirm,
}: {
  pending: PendingToggle | null;
  onCancel(): void;
  /** `withQuestions`: hide them (off) or show them again (on). */
  onConfirm(withQuestions: boolean): void;
}) {
  return (
    <Dialog open={pending !== null} onOpenChange={(open) => (open ? null : onCancel())}>
      {pending ? (
        <ToggleBody
          key={pending.label + pending.mode}
          pending={pending}
          onCancel={onCancel}
          onConfirm={onConfirm}
        />
      ) : null}
    </Dialog>
  );
}

function ToggleBody({
  pending,
  onCancel,
  onConfirm,
}: {
  pending: PendingToggle;
  onCancel(): void;
  onConfirm(withQuestions: boolean): void;
}) {
  // Off defaults to keeping questions; on defaults to showing them again.
  const [withQuestions, setWithQuestions] = useState(pending.mode === "on");
  const off = pending.mode === "off";
  const plural = pending.count === 1 ? "question" : "questions";

  const options = off
    ? [
        {
          value: false,
          title: "Stop new questions",
          detail: `The ${pending.count} existing ${plural} ${pending.count === 1 ? "stays" : "stay"} in the bank.`,
        },
        {
          value: true,
          title: `Also hide the ${pending.count} existing ${plural} from students`,
          detail: "They stay in the bank. You can show them again later.",
        },
      ]
    : [
        {
          value: true,
          title: `Show the ${pending.count} hidden ${plural} to students again`,
          detail: "They are served again.",
        },
        { value: false, title: "Keep them hidden", detail: "Only new questions use it." },
      ];

  return (
    <DialogContent className="sm:max-w-md">
      <DialogHeader>
        <DialogTitle>
          Turn {off ? "off" : "on"} “{pending.label}”
        </DialogTitle>
        <DialogDescription>
          For {pending.scopeLabel} · {pending.count} {off ? "approved" : "hidden"} {plural}
        </DialogDescription>
      </DialogHeader>

      <fieldset className="flex flex-col gap-2">
        <legend className="sr-only">What happens to existing questions</legend>
        {options.map((option) => (
          <label
            key={String(option.value)}
            className={cn(
              "flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5",
              withQuestions === option.value && "border-[var(--accent-solid)] bg-muted/40",
            )}
          >
            <input
              type="radio"
              name="existing"
              className="mt-1 accent-[var(--accent-solid)]"
              checked={withQuestions === option.value}
              onChange={() => setWithQuestions(option.value)}
            />
            <span>
              <span className="block font-medium text-sm">{option.title}</span>
              <span className="block text-muted-foreground text-xs">{option.detail}</span>
            </span>
          </label>
        ))}
      </fieldset>

      {off && withQuestions && pending.slotsBelowTarget > 0 ? (
        <p className="text-[var(--warn-solid)] text-sm">
          {pending.slotsBelowTarget} subtopic{" "}
          {pending.slotsBelowTarget === 1 ? "level falls" : "levels fall"} below target. The next
          round refills them.
        </p>
      ) : null}

      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="button" onClick={() => onConfirm(withQuestions)}>
          Turn {off ? "off" : "on"}
        </Button>
      </DialogFooter>
    </DialogContent>
  );
}
