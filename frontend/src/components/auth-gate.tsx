"use client";

/**
 * Keeps the professor console behind a login, without any Next.js middleware.
 *
 * Middleware can't do this job here: the session cookie is httpOnly and only
 * meaningful to FastAPI, so the only way to know it's valid is to ask the
 * backend (`GET /api/auth/me`). `StudentChrome`'s routes never render this --
 * students reach their sessions anonymously by link (ADR-041) and must never
 * be asked to log in.
 */

import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useCurrentUser } from "@/lib/api/queries";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const currentUser = useCurrentUser();

  useEffect(() => {
    if (currentUser.isError) router.replace("/login" as Route);
  }, [currentUser.isError, router]);

  if (currentUser.isSuccess) return <>{children}</>;
  // Loading and error both render nothing rather than a flash of the console
  // -- the error case is about to redirect.
  return null;
}
