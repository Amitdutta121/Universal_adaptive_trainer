/**
 * Turning JSON a professor supplies into the file an import endpoint takes.
 *
 * Both documents this console uploads — a book (`app/ingestion/schema.py`) and a
 * taxonomy (`app/curriculum/taxonomy_schema.py`) — arrive one of two ways: as a
 * `.json` file the professor saved, or as text pasted straight out of a chat with
 * an assistant. Both endpoints take a multipart upload, so pasted text becomes a
 * `File` here.
 *
 * What this deliberately does not do is validate either document. Both schemas
 * are the backend's, a second copy of those rules in the browser would drift from
 * them, and a client that pre-approves a document it does not own would be lying.
 * The two checks below are the ones that need no knowledge of a contract: is this
 * JSON at all, and will the upload be refused for its size before it is read.
 */

/**
 * Upload pasted text under a name the endpoint accepts.
 *
 * `filename` has no default on purpose: a silent one is how a taxonomy ends up
 * uploaded as `pasted-book.json`. Each caller names its own document.
 */
export function fileFromPastedJson(text: string, filename: string): File {
  return new File([text], filename, { type: "application/json" });
}

/**
 * Why this text cannot be uploaded as it stands, or `null` when it can be tried.
 *
 * Only structural JSON problems — an unparseable reply, or one that is not a JSON
 * object. Everything else is the validator's call. `noun` names the document in
 * the one message that has to mention it, so each screen stays as specific as it
 * would be with its own copy of these rules.
 */
export function jsonProblem(text: string, noun = "document"): string | null {
  const trimmed = text.trim();
  if (!trimmed) return "Paste the document, or choose a file.";

  if (trimmed.startsWith("```")) {
    return "This still has a markdown code fence around it. Paste the JSON only.";
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch (error) {
    return `This is not valid JSON: ${error instanceof Error ? error.message : String(error)}`;
  }

  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    return `A ${noun} must be a JSON object.`;
  }
  return null;
}

/** Whether an upload of this size will be refused before it is read. */
export function exceedsUploadLimit(bytes: number, maxUploadMb: number): boolean {
  return bytes > maxUploadMb * 1024 * 1024;
}
