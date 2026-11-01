/**
 * Forwards the incoming request's cookies to a server-side API call.
 *
 * A Server Component's own `fetch` calls never carry the browser's cookies --
 * unlike a same-origin browser request, there is no ambient session to reuse, so
 * a professor-only endpoint called from a Server Component 401s unless the
 * incoming request's `Cookie` header is attached explicitly. Import this only
 * from Server Components (`page.tsx` files that fetch directly); it depends on
 * `next/headers`, which breaks the build if pulled into a "use client" module.
 */

import { headers } from "next/headers";
import { COURSE_HEADER } from "@/lib/api/client";

export async function forwardedCookieHeader(): Promise<Record<string, string>> {
  const cookie = (await headers()).get("cookie");
  return cookie ? { Cookie: cookie } : {};
}

/**
 * The cookie plus the course the page belongs to. The browser client reads the
 * course from `window.location`; a Server Component has no window, so a page under
 * `/courses/[courseId]` passes its own `courseId` param here.
 */
export async function courseRequestHeaders(courseId: string): Promise<Record<string, string>> {
  return { ...(await forwardedCookieHeader()), [COURSE_HEADER]: courseId };
}
