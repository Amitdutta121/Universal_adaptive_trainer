"use client";

import { LogIn } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AuthCard, authLinkClass } from "@/components/auth-card";
import { QueryError } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useLogin } from "@/lib/api/queries";

export function LoginScreen() {
  const router = useRouter();
  const login = useLogin();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const submit = async () => {
    if (!email.trim() || !password) return;
    try {
      await login.mutateAsync({ email: email.trim(), password });
      // Every professor screen works inside a course, so signing in lands on
      // the course list rather than on any one course's screens.
      router.push("/courses" as Route);
    } catch {
      // Mutation state already carries the error for rendering below.
    }
  };

  return (
    <AuthCard subtitle="Sign in to the Instructor Studio.">
      <div className="space-y-2">
        <Label htmlFor="login-email">Email</Label>
        <Input
          id="login-email"
          type="email"
          autoComplete="username"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="dev@local.test"
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              void submit();
            }
          }}
        />
      </div>
      <div className="space-y-2">
        <div className="flex items-baseline justify-between">
          <Label htmlFor="login-password">Password</Label>
          <Link href={"/forgot-password" as Route} className={authLinkClass}>
            Forgot password?
          </Link>
        </div>
        <Input
          id="login-password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              void submit();
            }
          }}
        />
      </div>

      {login.isError ? <QueryError error={login.error} /> : null}

      <Button
        type="button"
        className="w-full"
        disabled={!email.trim() || !password || login.isPending}
        onClick={() => void submit()}
      >
        <LogIn />
        Sign in
      </Button>

      <p className="text-center text-muted-foreground text-sm">
        New here?{" "}
        <Link href={"/register" as Route} className={authLinkClass}>
          Create an account
        </Link>
      </p>
    </AuthCard>
  );
}
