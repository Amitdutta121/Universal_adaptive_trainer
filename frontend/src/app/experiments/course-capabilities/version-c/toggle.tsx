"use client";

import { cn } from "@/lib/utils";

/**
 * A small on/off switch. The app has no switch component, so this is a plain
 * `<button role="switch">`: Space/Enter toggle it, and `aria-checked` carries the state.
 */
export function Toggle({
  checked,
  onChange,
  disabled = false,
  label,
  describedBy,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
  /** Accessible name, e.g. "Python tests". */
  label: string;
  describedBy?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      aria-describedby={describedBy}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border outline-none transition-colors",
        "focus-visible:ring-3 focus-visible:ring-ring/50",
        "disabled:cursor-not-allowed disabled:opacity-40",
        checked
          ? "border-transparent bg-primary"
          : "border-transparent bg-[color-mix(in_oklch,var(--muted-foreground)_35%,transparent)]",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "inline-block size-3.5 rounded-full bg-background shadow-sm transition-transform",
          checked ? "translate-x-[18px]" : "translate-x-[2px]",
        )}
      />
    </button>
  );
}
