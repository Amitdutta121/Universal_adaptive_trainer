"use client";

/**
 * A compact −/+ counter for one difficulty on one chunk.
 *
 * Deliberately not an `<input type="number">`: the sheet has three of these per
 * row and a professor adjusts them by tapping, not by typing. It stays a real
 * control all the same — both buttons are focusable and labelled, so the sheet is
 * usable from the keyboard.
 */

import { Minus, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";

export function DifficultyStepper({
  value,
  onChange,
  label,
  max,
  disabled = false,
}: {
  value: number;
  onChange: (value: number) => void;
  /** Names what is being counted, for screen readers: "medium questions, 4.3 Loops". */
  label: string;
  max: number;
  disabled?: boolean;
}) {
  const isSet = value > 0;

  return (
    <span className="inline-flex items-center overflow-hidden rounded-md border border-border/80 bg-background">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="size-6 rounded-none text-muted-foreground hover:text-foreground"
        aria-label={`One fewer ${label}`}
        disabled={disabled || value === 0}
        onClick={() => onChange(value - 1)}
      >
        <Minus className="size-3" />
      </Button>
      <output
        aria-label={label}
        className={[
          "min-w-7 px-1 text-center font-mono text-xs tabular-nums",
          isSet ? "bg-accent/60 font-semibold text-primary" : "text-muted-foreground",
        ].join(" ")}
      >
        {value}
      </output>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="size-6 rounded-none text-muted-foreground hover:text-foreground"
        aria-label={`One more ${label}`}
        disabled={disabled || value >= max}
        onClick={() => onChange(value + 1)}
      >
        <Plus className="size-3" />
      </Button>
    </span>
  );
}
