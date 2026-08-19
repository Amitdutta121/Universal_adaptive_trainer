/**
 * The one upload decision specific to a taxonomy document.
 *
 * The structural JSON checks and the pasted-text-to-`File` conversion are shared
 * with the book upload and live in `lib/json-document.ts`. What is specific here
 * is the filename a pasted taxonomy travels under — distinct from the book one so
 * a rejected upload is traceable to the screen that sent it.
 *
 * There is deliberately no `labelOverride` counterpart to the book's
 * `titleOverride`: a taxonomy document declares its own `label`, the import takes
 * no override, and a wrong label is corrected by renaming the version afterwards.
 */

/** The name a pasted taxonomy document is uploaded under. `.json` is the only accepted extension. */
export const PASTED_TAXONOMY_FILENAME = "pasted-taxonomy.json";
