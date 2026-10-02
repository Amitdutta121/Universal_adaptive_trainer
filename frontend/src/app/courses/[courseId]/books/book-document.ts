/**
 * The two decisions a *book* upload makes that a taxonomy upload does not.
 *
 * The structural JSON checks and the pasted-text-to-`File` conversion are shared
 * with the curriculum upload and live in `lib/json-document.ts`. What stays here
 * is what is specific to `POST /api/books`: the name a pasted book is uploaded
 * under, and the fact that its `title` field is an override with a documented
 * blank meaning, which the taxonomy import does not have.
 */

/** The name a pasted book document is uploaded under. `.json` is the only accepted extension. */
export const PASTED_BOOK_FILENAME = "pasted-book.json";

/**
 * The title to send with an upload, or `undefined` to keep the document's own.
 *
 * Sending a blank title would be indistinguishable from sending none, and the
 * backend already falls back to the document's title, so blank means "omit".
 */
export function titleOverride(input: string): string | undefined {
  return input.trim() || undefined;
}
