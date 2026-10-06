"use client";

/**
 * "Verify your email" for an account that has not opened its verification link (ADR-061).
 *
 * Until it does, every route that spends LLM credit answers 403 `email_not_verified`; the rest
 * of the Studio works. Dismissing hides the banner for this browser tab's session only, so it
 * comes back next time rather than being forgotten for good.
 */

import { MailWarning, X } from "lucide-react";
import { useState } from "react";
import { QueryError } from "@/components/query-state";
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useCurrentUser, useRequestVerifyEmail } from "@/lib/api/queries";

const DISMISSED_KEY = "verify-email-banner-dismissed";

function readDismissed(): string | null {
  try {
    return typeof window === "undefined" ? null : window.sessionStorage.getItem(DISMISSED_KEY);
  } catch {
    return null;
  }
}

export function VerifyEmailBanner() {
  const currentUser = useCurrentUser();
  const resend = useRequestVerifyEmail();
  // The id of the account the banner was dismissed for, so another login still sees it.
  const [dismissedFor, setDismissedFor] = useState(readDismissed);

  const user = currentUser.data;
  if (!user || user.is_verified || dismissedFor === user.id) return null;

  const dismiss = () => {
    setDismissedFor(user.id);
    try {
      window.sessionStorage.setItem(DISMISSED_KEY, user.id);
    } catch {
      // Storage unavailable: dismissed for this page view only.
    }
  };

  return (
    <Alert>
      <MailWarning />
      <AlertTitle>Verify your email address</AlertTitle>
      <AlertDescription>
        <p>
          We sent a link to {user.email}. Until you open it, question generation and the other AI
          features are turned off.
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            disabled={resend.isPending}
            onClick={() => resend.mutate(user.email)}
          >
            Resend the link
          </Button>
          {resend.isSuccess ? <span>A new link is on its way.</span> : null}
        </div>
        {resend.isError ? (
          <div className="mt-2">
            <QueryError error={resend.error} />
          </div>
        ) : null}
      </AlertDescription>
      <AlertAction>
        <Button variant="ghost" size="icon-sm" onClick={dismiss} title="Dismiss">
          <X />
          <span className="sr-only">Dismiss</span>
        </Button>
      </AlertAction>
    </Alert>
  );
}
