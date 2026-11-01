import { Badge } from "@/components/ui/badge";

/** "Not built yet": a planned capability with no grader. */
export function PlannedBadge() {
  return (
    <Badge variant="outline" className="border-dashed text-muted-foreground">
      Not built yet
    </Badge>
  );
}

/** The LLM rubric grader: never counts toward mastery. */
export function AiGradedBadge() {
  return (
    <Badge
      className="bg-[var(--warn-wash)] text-[var(--warn-solid)]"
      title="Scores from this grader never count toward mastery"
    >
      AI-graded · practice only
    </Badge>
  );
}
