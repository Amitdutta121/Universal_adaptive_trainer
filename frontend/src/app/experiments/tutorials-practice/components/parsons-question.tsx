"use client";

import { ArrowDown, ArrowUp } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import type { ParsonsQuestion as ParsonsQuestionData } from "../mock-data";
import { move } from "../practice-logic";
import { CodeLines } from "./code-view";

/**
 * A Parsons problem: the lines of a working program in the wrong order. Each line keeps its own
 * indentation; the student only orders them, with Move up / Move down buttons (no dragging, so it
 * works from a keyboard and on a phone). Focus stays on the button that was pressed.
 */
export function ParsonsQuestion({
  question,
  order,
  onOrder,
  locked,
}: {
  question: ParsonsQuestionData;
  order: string[];
  onOrder: (order: string[]) => void;
  locked: boolean;
}) {
  const refocus = useRef<{ id: string; dir: "up" | "down" } | null>(null);
  const [announcement, setAnnouncement] = useState("");

  // biome-ignore lint/correctness/useExhaustiveDependencies: run after every reorder
  useEffect(() => {
    const target = refocus.current;
    if (!target) return;
    refocus.current = null;
    const button = document.querySelector<HTMLButtonElement>(
      `[data-line-id="${target.id}"] [data-dir="${target.dir}"]:not(:disabled)`,
    );
    (
      button ??
      document.querySelector<HTMLButtonElement>(
        `[data-line-id="${target.id}"] button:not(:disabled)`,
      )
    )?.focus();
  }, [order]);

  const shift = (from: number, to: number) => {
    const id = order[from];
    refocus.current = { id, dir: to < from ? "up" : "down" };
    setAnnouncement(`Moved to position ${to + 1} of ${order.length}.`);
    onOrder(move(order, from, to));
  };

  return (
    <>
      <p className="font-medium text-foreground">{question.goal}</p>
      <ol className="space-y-1.5" aria-label="Lines of the program, in their current order">
        {order.map((id, position) => {
          const line = question.lines.find((l) => l.id === id);
          if (!line) return null;
          const label = line.text.trim();
          return (
            <li
              key={id}
              data-line-id={id}
              className="flex items-center gap-2 rounded-lg border border-border bg-muted/60 py-1 pr-1.5 pl-1"
            >
              <span
                aria-hidden="true"
                className="w-5 text-center font-mono text-muted-foreground text-xs"
              >
                {position + 1}
              </span>
              <div className="min-w-0 flex-1 overflow-x-auto">
                <CodeLines code={line.text} numbers={false} />
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                data-dir="up"
                disabled={locked || position === 0}
                onClick={() => shift(position, position - 1)}
                aria-label={`Move up: ${label}`}
              >
                <ArrowUp aria-hidden="true" />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                data-dir="down"
                disabled={locked || position === order.length - 1}
                onClick={() => shift(position, position + 1)}
                aria-label={`Move down: ${label}`}
              >
                <ArrowDown aria-hidden="true" />
              </Button>
            </li>
          );
        })}
      </ol>
      <p aria-live="polite" className="sr-only">
        {announcement}
      </p>
    </>
  );
}
