"use client";

/** Switches between the five decks: a segmented control on wide screens, a select on a phone. */

import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Topic } from "../mock-data";

export function TopicPicker({
  topics,
  activeId,
  done,
  onSelect,
}: {
  topics: Topic[];
  activeId: string;
  done: string[];
  onSelect: (id: string) => void;
}) {
  return (
    <nav aria-label="Topics">
      <ul className="hidden gap-1 rounded-lg bg-muted p-0.5 sm:flex">
        {topics.map((topic) => {
          const active = topic.id === activeId;
          return (
            <li key={topic.id} className="flex-1">
              <button
                type="button"
                aria-current={active ? "true" : undefined}
                onClick={() => onSelect(topic.id)}
                className={cn(
                  "flex h-8 w-full items-center justify-center gap-1.5 rounded-md px-2 font-medium text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
                  active
                    ? "bg-background text-foreground shadow-xs"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {topic.label}
                {done.includes(topic.id) ? (
                  <>
                    <Check aria-hidden="true" className="size-3.5 text-primary" />
                    <span className="sr-only">, done</span>
                  </>
                ) : null}
              </button>
            </li>
          );
        })}
      </ul>
      <div className="sm:hidden">
        <label htmlFor="topic-select" className="sr-only">
          Topic
        </label>
        <select
          id="topic-select"
          value={activeId}
          onChange={(event) => onSelect(event.target.value)}
          className="h-9 w-full rounded-lg border border-input bg-background px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          {topics.map((topic) => (
            <option key={topic.id} value={topic.id}>
              {topic.label}
              {done.includes(topic.id) ? " (done)" : ""}
            </option>
          ))}
        </select>
      </div>
    </nav>
  );
}
