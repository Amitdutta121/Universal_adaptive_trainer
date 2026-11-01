"use client";

/** A small accessible on/off switch. The app has no switch component, so this lives here. */

import { cn } from "@/lib/utils";

interface ToggleProps {
  checked: boolean;
  onCheckedChange: (next: boolean) => void;
  disabled?: boolean;
  /** Accessible name, e.g. "Choice" or "Allow Multiple choice". */
  label: string;
  /** Id of an element that describes the toggle (the capability card, the reason a type is off). */
  describedBy?: string;
  size?: "sm" | "default";
}

export function Toggle({
  checked,
  onCheckedChange,
  disabled = false,
  label,
  describedBy,
  size = "default",
}: ToggleProps) {
  const small = size === "sm";
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      aria-describedby={describedBy}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "relative inline-flex shrink-0 items-center rounded-full border transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50",
        small ? "h-4 w-7" : "h-5 w-9",
        checked ? "border-transparent bg-primary" : "border-border bg-muted",
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "inline-block rounded-full bg-background shadow-sm transition-transform",
          small ? "size-3" : "size-4",
          checked ? (small ? "translate-x-3" : "translate-x-4") : "translate-x-0.5",
        )}
      />
    </button>
  );
}
