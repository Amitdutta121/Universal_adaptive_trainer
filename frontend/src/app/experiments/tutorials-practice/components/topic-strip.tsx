import { cn } from "@/lib/utils";
import { BANK, TOPICS } from "../mock-data";
import type { Outcome, Stats } from "../practice-logic";

const WORD: Record<Outcome, string> = {
  right: "right",
  recovered: "right on the second try",
  missed: "missed",
};

/**
 * A quiet per-topic strip: one dot per question of the topic. Filled = right first try, outlined =
 * right on the second try, red = missed, empty = still to do. Nothing here is a score or a grade.
 *
 * TODO(real): the dots come from a two-line heuristic on the answers (see `practice-logic.ts`); the
 * real system would show measured mastery, or nothing at all.
 */
export function TopicStrip({ stats }: { stats: Stats }) {
  return (
    <ul aria-label="Progress by topic" className="flex flex-wrap gap-x-5 gap-y-1.5">
      {TOPICS.map((topic) => {
        const total = BANK.filter((q) => q.topic === topic.id).length;
        const results = stats[topic.id].results;
        const summary = results.length
          ? results.map((r) => WORD[r]).join(", ")
          : "nothing answered yet";
        return (
          <li key={topic.id} className="flex items-center gap-2 text-muted-foreground text-xs">
            <span>{topic.label}</span>
            <span aria-hidden="true" className="flex gap-1">
              {Array.from({ length: total }, (_, i) => {
                const result = results[i];
                return (
                  <span
                    // biome-ignore lint/suspicious/noArrayIndexKey: fixed-length list of dots
                    key={i}
                    className={cn(
                      "size-2 rounded-full border",
                      !result && "border-border",
                      result === "right" && "border-primary bg-primary",
                      result === "recovered" && "border-primary bg-transparent",
                      result === "missed" && "border-destructive bg-destructive",
                    )}
                  />
                );
              })}
            </span>
            <span className="sr-only">{`${topic.label}: ${summary}`}</span>
          </li>
        );
      })}
    </ul>
  );
}
