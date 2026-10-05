"use client";

import { UserPlus } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AuthCard, authLinkClass, MIN_PASSWORD_LENGTH } from "@/components/auth-card";
import { QueryError } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useRegister } from "@/lib/api/queries";

export function RegisterScreen() {
  const router = useRouter();
  const register = useRegister();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!email.trim() || !password) return;
    try {
      await register.mutateAsync({ email: email.trim(), password });
      // Signed in already; the course list shows the "verify your email" banner.
      router.push("/courses" as Route);
    } catch {
      // Mutation state already carries the error for rendering below.
    }
  };

  return (
    <AuthCard subtitle="Create an Instructor Studio account.">
      <form className="space-y-4" onSubmit={(event) => void submit(event)}>
        <div className="space-y-2">
          <Label htmlFor="register-email">Email</Label>
          <Input
            id="register-email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@university.edu"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="register-password">Password</Label>
          <Input
            id="register-password"
            type="password"
            autoComplete="new-password"
            required
            aria-describedby="register-password-hint"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <p id="register-password-hint" className="text-muted-foreground text-xs">
            At least {MIN_PASSWORD_LENGTH} characters.
          </p>
        </div>

        {register.isError ? <QueryError error={register.error} /> : null}

        <Button
          type="submit"
          className="w-full"
          disabled={!email.trim() || !password || register.isPending}
        >
          <UserPlus />
          Create account
        </Button>
      </form>

      <p className="text-center text-muted-foreground text-sm">
        Already have an account?{" "}
        <Link href={"/login" as Route} className={authLinkClass}>
          Sign in
        </Link>
      </p>
    </AuthCard>
  );
}
