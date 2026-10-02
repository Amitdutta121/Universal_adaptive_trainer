"use client";

/**
 * Why the server would not save or import a taxonomy, as a professor would want it said.
 *
 * A refusal for the document's content lists each problem as a sentence
 * (`taxonomy-refusal.ts`), under a heading that says plainly that nothing was saved. Any other
 * failure — the API unreachable, a file too large, text that is not JSON — is shown exactly as
 * `QueryError` shows every other API error, because that wording is already a sentence.
 */

import { AlertCircle } from "lucide-react";
import { QueryError } from "@/components/query-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { readApiError } from "@/lib/api/client";
import { explainRefusal, type NamedDocument } from "../taxonomy-refusal";

/** The code the backend gives a document that broke the taxonomy rules. */
const INVALID_DOCUMENT = "invalid_taxonomy_document";

export function TaxonomyRefusalAlert({
  error,
  doc,
  heading,
}: {
  error: unknown;
  /** The document that was sent, so problems can name the topic they are about. */
  doc?: NamedDocument | null;
  heading: string;
}) {
  const apiError = readApiError(error);
  if (!apiError || apiError.code !== INVALID_DOCUMENT || !apiError.detail) {
    return <QueryError error={error} />;
  }

  const problems = explainRefusal(apiError.detail, doc);
  return (
    <Alert variant="destructive">
      <AlertCircle />
      <AlertTitle>{heading}</AlertTitle>
      <AlertDescription>
        <ul className="list-disc space-y-1 pl-4">
          {problems.map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  );
}
