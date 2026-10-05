"use client";

import { CircleCheck, KeyRound } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { useState } from "react";
import { AuthCard, authLinkClass, MIN_PASSWORD_LENGTH } from "@/components/auth-card";
import { QueryError } from "@/components/query-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useResetPassword } from "@/lib/api/queries";

export function ResetPasswordScreen({ token }: { token: string }) {
  const reset = useResetPassword();
  const [password, setPassword] = useState("");

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (password) reset.mutate({ token, password });
  };

  if (reset.isSuccess) {
    return (
      <AuthCard subtitle="Reset your password.">
        <Alert>
          <CircleCheck />
          <AlertTitle>Your password has been changed.</AlertTitle>
          <AlertDescription>Sign in with the new password.</AlertDescription>
        </Alert>
        <Button asChild className="w-full">
          <Link href={"/login" as Route}>Sign in</Link>
        </Button>
      </AuthCard>
    );
  }

  return (
    <AuthCard subtitle="Choose a new password.">
      {!token ? (
        <Alert variant="destructive">
          <AlertTitle>This link is incomplete.</AlertTitle>
          <AlertDescription>
            Open the link from the email again, or ask for a new one.
          </AlertDescription>
        </Alert>
      ) : (
        <form className="space-y-4" onSubmit={submit}>
          <div className="space-y-2">
            <Label htmlFor="reset-password">New password</Label>
            <Input
              id="reset-password"
              type="password"
              autoComplete="new-password"
              required
              aria-describedby="reset-password-hint"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            <p id="reset-password-hint" className="text-muted-foreground text-xs">
              At least {MIN_PASSWORD_LENGTH} characters.
            </p>
          </div>

          {reset.isError ? <QueryError error={reset.error} /> : null}

          <Button type="submit" className="w-full" disabled={!password || reset.isPending}>
            <KeyRound />
            Change password
          </Button>
        </form>
      )}

      <p className="text-center">
        <Link href={"/forgot-password" as Route} className={authLinkClass}>
          Get a new reset link
        </Link>
      </p>
    </AuthCard>
  );
}
