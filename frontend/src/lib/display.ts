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
  // The API sends UTC times without a zone marker ("2026-09-24T01:41:00"). `new Date` reads such a
  // string as *local* time, which shows a professor a time hours off from the one they saw.
  const at = new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(iso) ? iso : `${iso}Z`);
  return Number.isNaN(at.getTime())
    ? "—"
    : at.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function pluralise(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

/** A machine code as prose: `producer_inferred` reads as `producer inferred`. */
export function codeLabel(code: string): string {
  return code.replace(/_/g, " ");
}
