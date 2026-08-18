"use client";

/**
 * The three states every API-backed view has to render, in one place.
 *
 * An error is shown with the backend's own message and detail. The API states why
 * it refused — an invalid document, a question with no verdict, an unreachable
 * provider — and that text is more useful to a professor than "something went wrong".
 */

import { AlertCircle, Inbox } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";

export function QueryError({ error }: { error: unknown }) {
  const apiError = error instanceof ApiError ? error : null;
  const title = apiError
    ? apiError.isUpstream
      ? "The model provider could not be reached"
      : apiError.isNotImplemented
        ? "Not available yet"
        : apiError.message
    : "The API could not be reached";

  return (
    <Alert variant="destructive">
      <AlertCircle />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>
        {apiError ? (
          <div className="space-y-1">
            {apiError.detail ? <p className="whitespace-pre-wrap">{apiError.detail}</p> : null}
            <p className="font-mono text-xs opacity-70">
              {apiError.code} · HTTP {apiError.status}
            </p>
          </div>
        ) : (
          <p>Check that the FastAPI application is running on {"http://127.0.0.1:8000"}.</p>
        )}
      </AlertDescription>
    </Alert>
  );
}

export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }, (_, index) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: placeholder rows have no identity
        <Skeleton key={index} className="h-11 w-full" />
      ))}
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed py-12 text-center">
      <Inbox className="size-6 text-muted-foreground" />
      <p className="font-medium text-sm">{title}</p>
      {hint ? <p className="max-w-sm text-muted-foreground text-sm">{hint}</p> : null}
    </div>
  );
}

/**
 * A screen that is deliberately not built yet.
 *
 * The backend's rule that a placeholder must raise rather than return invented data
 * applies to the UI too: a page with no implementation says so, instead of rendering
 * an empty table that reads as "there is nothing here".
 */
export function NotBuiltYet({ endpoints }: { endpoints: readonly string[] }) {
  return (
    <Alert>
      <AlertCircle />
      <AlertTitle>This screen has not been built yet</AlertTitle>
      <AlertDescription>
        <p>
          The starter wires up the shell, the typed client and the query layer. This section is
          still served by the Jinja UI. Its API is already generated and typed:
        </p>
        <ul className="mt-2 space-y-0.5 font-mono text-xs">
          {endpoints.map((endpoint) => (
            <li key={endpoint}>{endpoint}</li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  );
}
