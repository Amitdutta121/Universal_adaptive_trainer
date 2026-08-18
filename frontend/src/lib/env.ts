/**
 * The only module that reads the environment, mirroring `app/config.py` on the
 * backend: everything else imports these values.
 */

/**
 * Where the FastAPI application lives, as seen from the Next.js server process.
 *
 * Only used for server-side (RSC / route handler) requests. Browser requests go to
 * the same origin and are forwarded by the rewrite in `next.config.ts`, so the
 * browser never needs this and CORS is never involved in development.
 */
export const API_ORIGIN = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";

/** True while rendering on the Next.js server (RSC, route handlers, tests). */
export const IS_SERVER = typeof window === "undefined";

/**
 * Base URL for the typed API client.
 *
 * Empty on the browser so requests stay same-origin and hit the rewrite; absolute
 * on the server because there is no origin to be relative to.
 */
export const API_BASE_URL = IS_SERVER ? API_ORIGIN : "";
