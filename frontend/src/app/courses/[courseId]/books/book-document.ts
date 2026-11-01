/**
 * What is specific to `POST /api/books`: its `title` field is an override with a
 * documented blank meaning, which the taxonomy import does not have.
 */

/**
 * The title to send with an upload, or `undefined` to keep the document's own.
 *
 * Sending a blank title would be indistinguishable from sending none, and the
 * backend already falls back to the document's title, so blank means "omit".
 */
export function titleOverride(input: string): string | undefined {
  return input.trim() || undefined;
}
