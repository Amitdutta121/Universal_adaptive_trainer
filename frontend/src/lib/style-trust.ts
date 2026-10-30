import type { StyleTrust } from "@/lib/api/types";

/**
 * What a question style is still waiting on before its questions skip review.
 *
 * Every window, custom rules included, must be trusted, so the shortest one is what the style is
 * still waiting on. Reviews pool across the course's taxonomies; the topic judge also needs a few
 * in the style row's own taxonomy (`min_topic_local`).
 */
export function styleStatus(style: StyleTrust, minimum: number, topicMinimum: number): string {
  const windows = Object.values(style.metrics);
  if (style.trusted) return "Skips review";
  if (windows.some((metric) => metric.audit_revoked)) return "Audit failed";
  const fewest = Math.min(...windows.map((metric) => metric.observations));
  if (fewest < minimum) return `Building trust: ${fewest} of ${minimum} reviews`;
  const here = style.metrics.subtopic?.local_observations ?? 0;
  if (here < topicMinimum) return `Topic check: ${here} of ${topicMinimum} in this taxonomy`;
  return "Below 90% agreement";
}
