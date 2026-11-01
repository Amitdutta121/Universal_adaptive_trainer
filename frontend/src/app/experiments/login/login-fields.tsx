"use client";

/** The email + password fields, error, and submit button every version shares. */

import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { MockLogin } from "./mock-login";

export const linkClass = "font-medium text-primary text-sm underline-offset-4 hover:underline";

export function LoginFields({
  login,
  idPrefix,
  hideEmail = false,
  autoFocusPassword = false,
  submitLabel = "Sign in",
}: {
  login: MockLogin;
  idPrefix: string;
  hideEmail?: boolean;
  autoFocusPassword?: boolean;
  submitLabel?: string;
}) {
  if (login.status === "done") {
    return (
      <Alert>
        <CheckCircle2 className="text-primary" />
        <AlertTitle>Signed in (mock)</AlertTitle>
        <AlertDescription>The real page would go to your course list now.</AlertDescription>
      </Alert>
    );
  }

  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault();
        login.submit();
      }}
    >
      {login.errorText ? (
        <Alert variant="destructive">
          <AlertCircle />
          <AlertTitle>Wrong email or password</AlertTitle>
          <AlertDescription>{login.errorText}</AlertDescription>
        </Alert>
      ) : null}
      {hideEmail ? null : (
        <div className="space-y-2">
          <Label htmlFor={`${idPrefix}-email`}>Email</Label>
          <Input
            id={`${idPrefix}-email`}
            type="email"
            autoComplete="username"
            placeholder="you@university.edu"
            value={login.email}
            onChange={(event) => login.setEmail(event.target.value)}
          />
        </div>
      )}
      <div className="space-y-2">
        <div className="flex items-baseline justify-between">
          <Label htmlFor={`${idPrefix}-password`}>Password</Label>
          <a href="#forgot" className={linkClass}>
            Forgot password?
          </a>
        </div>
        <Input
          id={`${idPrefix}-password`}
          type="password"
          autoComplete="current-password"
          autoFocus={autoFocusPassword}
          value={login.password}
          aria-invalid={login.status === "error" || undefined}
          onChange={(event) => login.setPassword(event.target.value)}
        />
      </div>
      <Button type="submit" className="w-full" disabled={!login.canSubmit}>
        {login.status === "pending" ? <Loader2 className="animate-spin" /> : null}
        {login.status === "pending" ? "Signing in…" : submitLabel}
      </Button>
    </form>
  );
}
