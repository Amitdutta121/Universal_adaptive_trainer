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

export async function forwardedCookieHeader(): Promise<Record<string, string>> {
  const cookie = (await headers()).get("cookie");
  return cookie ? { Cookie: cookie } : {};
}
