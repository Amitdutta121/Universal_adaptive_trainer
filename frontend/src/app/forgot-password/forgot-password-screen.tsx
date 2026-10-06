"use client";

import { Mail } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { useState } from "react";
import { AuthCard, authLinkClass } from "@/components/auth-card";
import { QueryError } from "@/components/query-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useForgotPassword } from "@/lib/api/queries";

export function ForgotPasswordScreen() {
  const forgot = useForgotPassword();
  const [email, setEmail] = useState("");

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (email.trim()) forgot.mutate(email.trim());
  };

  return (
    <AuthCard subtitle="Reset your password.">
      {forgot.isSuccess ? (
        // The same answer whether or not the address has an account (ADR-061).
        <Alert>
          <Mail />
          <AlertTitle>Check your email.</AlertTitle>
          <AlertDescription>
            If {forgot.variables} has an account, we sent it a link to choose a new password. The
            link works for one hour.
          </AlertDescription>
        </Alert>
      ) : (
        <form className="space-y-4" onSubmit={submit}>
          <div className="space-y-2">
            <Label htmlFor="forgot-email">Email</Label>
            <Input
              id="forgot-email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>

          {forgot.isError ? <QueryError error={forgot.error} /> : null}

          <Button type="submit" className="w-full" disabled={!email.trim() || forgot.isPending}>
            <Mail />
            Email me a reset link
          </Button>
        </form>
      )}

      <p className="text-center">
        <Link href={"/login" as Route} className={authLinkClass}>
          Back to sign in
        </Link>
      </p>
    </AuthCard>
  );
}
