"use client";

/** One segment per card. Segments are real buttons, so a student can jump back to any card. */

import { cn } from "@/lib/utils";

export function SegmentedProgress({
  total,
  index,
  onJump,
}: {
  total: number;
  index: number;
  onJump: (index: number) => void;
}) {
  const segments = Array.from({ length: total }, (_, position) => position + 1);
  return (
    <nav aria-label="Tutorial progress">
      <ol className="flex gap-1.5">
        {segments.map((number) => {
          const position = number - 1;
          return (
            <li key={number} className="flex-1">
              <button
                type="button"
                aria-label={`Go to card ${number} of ${total}`}
                aria-current={position === index ? "step" : undefined}
                onClick={() => onJump(position)}
                className="group flex h-6 w-full items-center rounded-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                <span
                  className={cn(
                    "block h-1.5 w-full rounded-full",
                    position <= index ? "bg-primary" : "bg-muted group-hover:bg-border",
                  )}
                />
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
