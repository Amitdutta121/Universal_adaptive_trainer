"use client";

/**
 * "Teaching the judges": one chip per question style of this taxonomy, saying how far its
 * reviews have got toward the judges' trust. A trusted style's new questions skip this queue
 * (one in ten still comes back as an audit), so the professor can see which reviews still count.
 */

import { Badge } from "@/components/ui/badge";
import { useJudgeStats } from "@/lib/api/queries";
import { styleStatus } from "@/lib/style-trust";

export function JudgeTrustStrip({ curriculumVersionId }: { curriculumVersionId: number | null }) {
  const { data: stats } = useJudgeStats();
  if (!stats || curriculumVersionId == null) return null;
  const styles = stats.styles.filter(
    (style) => style.curriculum_version_id === curriculumVersionId,
  );
  if (styles.length === 0) return null;
  return (
    <div className="space-y-2" data-testid="judge-trust-strip">
      <div className="text-muted-foreground text-sm">
        Teaching the judges: each style skips review after {stats.min_observations} reviews you
        agree with.
      </div>
      <ul className="flex flex-wrap gap-2">
        {styles.map((style) => (
          <li key={style.style_id}>
            <Badge variant={style.trusted ? "secondary" : "outline"} className="gap-1.5">
              <span className="font-medium">{style.style_name ?? style.style_id}</span>
              <span className="text-muted-foreground tabular-nums">
                {styleStatus(style, stats.min_observations, stats.min_topic_local)}
              </span>
            </Badge>
          </li>
        ))}
      </ul>
    </div>
  );
}
