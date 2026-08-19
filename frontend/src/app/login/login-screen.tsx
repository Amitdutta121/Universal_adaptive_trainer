"use client";

import { LogIn, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { QueryError } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
      // Not "/": there is no page at the bare root (see NAV_SECTIONS), so this
      // is the first real professor screen once signed in.
      router.push("/books");
    } catch {
      // Mutation state already carries the error for rendering below.
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <Card className="w-full max-w-sm border-border/70">
        <CardHeader className="items-center gap-2 text-center">
          <span className="flex size-10 items-center justify-center rounded-full bg-primary/10 text-primary">
            <Sparkles className="size-5" />
          </span>
          <CardTitle className="text-xl">Adaptive Trainer</CardTitle>
          <p className="text-muted-foreground text-sm">Sign in to the professor console.</p>
        </CardHeader>
        <CardContent className="space-y-4">
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
            <Label htmlFor="login-password">Password</Label>
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
        </CardContent>
      </Card>
    </div>
  );
}
