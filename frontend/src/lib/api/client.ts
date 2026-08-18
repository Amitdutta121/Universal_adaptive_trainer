/**
 * The single typed entry point to the FastAPI backend.
 *
 * Every path, query parameter, request body and response shape is checked against
 * `schema.d.ts`, which is compiled from the backend's own OpenAPI document by
 * `pnpm run api:types`. Nothing here restates a backend model by hand.
 *
 * No other module may call `fetch` against the API.
 */

import createClient, { type Middleware } from "openapi-fetch";
import { API_BASE_URL } from "@/lib/env";
import type { paths } from "./schema";

/** The error envelope produced by `app/errors.py`: `{"error": {code, message, detail?}}`. */
export interface ApiErrorBody {
  error: { code: string; message: string; detail?: string };
}

/** A failed API call, carrying the backend's own error vocabulary. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail?: string;

  constructor(status: number, code: string, message: string, detail?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }

  /** True when retrying could plausibly succeed — the LLM provider was unreachable. */
  get isUpstream(): boolean {
    return this.status === 502;
  }

  /** True when the backend has no implementation behind this route yet (ADR: placeholders raise). */
  get isNotImplemented(): boolean {
    return this.status === 501;
  }
}

/**
 * `app/errors.py` chooses between a JSON body and a rendered HTML error page by
 * inspecting the `Accept` header. Without this the client would receive an HTML
 * document for every 404 and fail to parse it.
 */
const acceptJson: Middleware = {
  async onRequest({ request }) {
    request.headers.set("Accept", "application/json");
    return request;
  },
};

/**
 * Build a client against an explicit origin.
 *
 * The application uses the `api` singleton below. This factory exists so tests can
 * supply an absolute base URL: the browser resolves the relative one used in
 * production against the current page, which jsdom will not do.
 */
export function createApiClient(baseUrl: string) {
  const client = createClient<paths>({ baseUrl });
  client.use(acceptJson);
  return client;
}

export const api = createApiClient(API_BASE_URL);

/** What `openapi-fetch` hands back: exactly one of `data` or `error` is set. */
type Result<T> = { data?: T; error?: unknown; response: Response };

function toApiError(status: number, body: unknown): ApiError {
  if (
    typeof body === "object" &&
    body !== null &&
    "error" in body &&
    typeof (body as ApiErrorBody).error === "object"
  ) {
    const { code, message, detail } = (body as ApiErrorBody).error;
    return new ApiError(status, code, message, detail);
  }
  // FastAPI's own request validation (422) uses `{"detail": [...]}`, which never
  // reaches the application handlers.
  if (typeof body === "object" && body !== null && "detail" in body) {
    return new ApiError(
      status,
      "validation_error",
      "The request was rejected as invalid.",
      JSON.stringify((body as { detail: unknown }).detail),
    );
  }
  return new ApiError(status, "unknown_error", `The API returned HTTP ${status}.`);
}

/**
 * Turn an `openapi-fetch` result into a value or a thrown `ApiError`.
 *
 * TanStack Query treats a rejected promise as the error state, so unwrapping here
 * keeps every caller free of `if (error)` branches.
 */
export async function unwrap<T>(call: Promise<Result<T>>): Promise<T> {
  const { data, error, response } = await call;
  if (error !== undefined || !response.ok) {
    throw toApiError(response.status, error);
  }
  return data as T;
}
