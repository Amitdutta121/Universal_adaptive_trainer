"use client";

import { CircleCheck } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { AuthCard, authLinkClass, authButtonClass } from "@/components/auth-card";
import { QueryError } from "@/components/query-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { readApiError } from "@/lib/api/client";
import { useCurrentUser, useVerifyEmail } from "@/lib/api/queries";

export function VerifyScreen({ token }: { token: string }) {
  const { mutateAsync: verify } = useVerifyEmail();
  const currentUser = useCurrentUser();
  // Once per page: a second call with the same token answers "already verified".
  const sent = useRef(false);
  // Held here rather than read off the mutation: under StrictMode the effect's remount
  // resubscribes the mutation observer, which then never reports this call's result.
  const [outcome, setOutcome] = useState<{ ok: true } | { error: unknown } | null>(null);

  useEffect(() => {
    if (!token || sent.current) return;
    sent.current = true;
    verify(token).then(
      () => setOutcome({ ok: true }),
      (error: unknown) => setOutcome({ error }),
    );
  }, [token, verify]);

  const error = outcome && "error" in outcome ? outcome.error : null;
  const alreadyVerified = readApiError(error)?.code === "verify_user_already_verified";
  const done = (outcome !== null && "ok" in outcome) || alreadyVerified;
  const next = currentUser.isSuccess
    ? { href: "/courses", label: "Go to your courses" }
    : { href: "/login", label: "Sign in" };

  return (
    <AuthCard subtitle="Email verification">
      {!token ? (
        <Alert variant="destructive">
          <AlertTitle>This link is incomplete.</AlertTitle>
          <AlertDescription>
            Open the link from the email again, or ask for a new one from the banner in the Studio.
          </AlertDescription>
        </Alert>
      ) : done ? (
        <Alert>
          <CircleCheck />
          <AlertTitle>Your email address is verified.</AlertTitle>
          <AlertDescription>Question generation and the other AI features are on.</AlertDescription>
        </Alert>
      ) : error ? (
        <QueryError error={error} />
      ) : (
        <p className="text-center text-base text-muted-foreground">Verifying your email address…</p>
      )}

      {done ? (
        <Button asChild className={authButtonClass}>
          <Link href={next.href as Route}>{next.label}</Link>
        </Button>
      ) : (
        <p className="text-center">
          <Link href={next.href as Route} className={authLinkClass}>
            {next.label}
          </Link>
        </p>
      )}
    </AuthCard>
  );
}
