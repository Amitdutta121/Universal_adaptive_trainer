/**
 * Formatting shared by every screen that lists rows the backend owns.
 *
 * Pure, and outside any feature folder, because a book, a curriculum version and
 * a question all show counts and timestamps and must show them the same way. What
 * stays in a feature's own display module is the wording that carries meaning
 * there — what `partial` means for a book, what `superseded` means for a
 * curriculum version.
 */

/**
 * A timestamp in the reader's own locale.
 *
 * Rendered on the client only: formatting on the server would use the server's
 * locale and time zone, and React would then complain about the mismatch. A
 * component that calls this needs `"use client"`.
 */
export function formatTimestamp(iso: string): string {
  const at = parseApiTime(iso);
  return Number.isNaN(at.getTime())
    ? "—"
    : at.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/** "just now", "6m ago", "2h ago", "3d ago" — for lists where recency matters more than the date. */
export function timeAgo(iso: string, now: number = Date.now()): string {
  const at = parseApiTime(iso).getTime();
  if (Number.isNaN(at)) return "—";
  const minutes = Math.round((now - at) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  if (minutes < 60 * 24) return `${Math.round(minutes / 60)}h ago`;
  return `${Math.round(minutes / (60 * 24))}d ago`;
}

/** "45s", "6m 3s", "1h 12m": how long something took or has been running. */
export function formatDuration(fromIso: string, toIso?: string | null, now: number = Date.now()): string {
  const from = parseApiTime(fromIso).getTime();
  const to = toIso ? parseApiTime(toIso).getTime() : now;
  if (Number.isNaN(from) || Number.isNaN(to)) return "—";
  const seconds = Math.max(0, Math.round((to - from) / 1000));
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  return `${Math.floor(seconds / 3600)}h ${Math.round((seconds % 3600) / 60)}m`;
}

function parseApiTime(iso: string): Date {
  // The API sends UTC times without a zone marker ("2026-09-24T01:41:00"). `new Date` reads such a
  // string as *local* time, which shows a professor a time hours off from the one they saw.
  return new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(iso) ? iso : `${iso}Z`);
}

export function pluralise(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

/** A machine code as prose: `producer_inferred` reads as `producer inferred`. */
export function codeLabel(code: string): string {
  return code.replace(/_/g, " ");
}
