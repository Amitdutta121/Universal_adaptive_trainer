import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { DIFFICULTIES, DIFFICULTY_LABEL, type Difficulty } from "../mock-types";

/** Difficulty as a 1-3 bar meter, so it reads without relying on colour. */
export function DifficultyBadge({ difficulty }: { difficulty: Difficulty }) {
  const level = DIFFICULTIES.indexOf(difficulty);
  return (
    <Badge variant="outline" className="gap-1.5">
      <span aria-hidden className="flex items-end gap-px">
        {DIFFICULTIES.map((entry, index) => (
          <span
            key={entry}
            className={cn(
              "w-[3px] rounded-[1px]",
              index === 0 ? "h-1.5" : index === 1 ? "h-2" : "h-2.5",
              index <= level ? "bg-[var(--accent-solid)]" : "bg-border",
            )}
          />
        ))}
      </span>
      {DIFFICULTY_LABEL[difficulty]}
    </Badge>
  );
}

export function TypeBadge({ label }: { label: string }) {
  return <Badge variant="secondary">{label}</Badge>;
}
