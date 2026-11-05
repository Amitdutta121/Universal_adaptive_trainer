import type { StyleTrust } from "@/lib/api/types";

/**
 * What a question style is still waiting on before its questions skip review, as a full sentence
 * and as a short chip label.
 *
 * Every window, custom rules included, must be trusted, so the shortest one is what the style is
 * still waiting on. Reviews pool across the course's taxonomies; the topic judge also needs a few
 * in the style row's own taxonomy (`min_topic_local`).
 */
export function styleTrustState(
  style: StyleTrust,
  minimum: number,
  topicMinimum: number,
): { full: string; short: string } {
  const windows = Object.values(style.metrics);
  if (style.trusted) return { full: "Skips review", short: "skips review" };
  if (windows.some((metric) => metric.audit_revoked))
    return { full: "Audit failed", short: "audit failed" };
  const fewest = Math.min(...windows.map((metric) => metric.observations));
  if (fewest < minimum)
    return {
      full: `Building trust: ${fewest} of ${minimum} reviews`,
      short: `${fewest}/${minimum}`,
    };
  const here = style.metrics.subtopic?.local_observations ?? 0;
  if (here < topicMinimum)
    return {
      full: `Topic check: ${here} of ${topicMinimum} in this taxonomy`,
      short: `topic ${here}/${topicMinimum}`,
    };
  return { full: "Below 90% agreement", short: "<90% agree" };
}

export function styleStatus(style: StyleTrust, minimum: number, topicMinimum: number): string {
  return styleTrustState(style, minimum, topicMinimum).full;
}
