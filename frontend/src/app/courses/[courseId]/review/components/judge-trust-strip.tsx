"use client";

/**
 * "Teaching the judges": one compact chip per question style of this taxonomy, saying how far its
 * reviews have got toward the judges' trust. A trusted style's new questions skip this queue
 * (one in ten still comes back as an audit). The full status is the chip's tooltip.
 */

import { useJudgeStats } from "@/lib/api/queries";
import { styleTrustState } from "@/lib/style-trust";

export function JudgeTrustStrip({ curriculumVersionId }: { curriculumVersionId: number | null }) {
  const { data: stats } = useJudgeStats();
  if (!stats || curriculumVersionId == null) return null;
  const styles = stats.styles.filter(
    (style) => style.curriculum_version_id === curriculumVersionId,
  );
  if (styles.length === 0) return null;
  return (
    <ul
      className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-xs"
      data-testid="judge-trust-strip"
      title={`Each style skips review after ${stats.min_observations} reviews you agree with.`}
    >
      {styles.map((style) => {
        const state = styleTrustState(style, stats.min_observations, stats.min_topic_local);
        return (
          <li key={style.style_id} title={state.full} className="whitespace-nowrap">
            <span className={style.trusted ? "text-[var(--review-accent)]" : undefined}>
              {style.style_name ?? style.style_id}
            </span>{" "}
            <span className="text-muted-foreground tabular-nums">{state.short}</span>
          </li>
        );
      })}
    </ul>
  );
}
