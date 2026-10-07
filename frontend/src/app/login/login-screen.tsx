"use client";

/**
 * Sign in, as two doors side by side: instructors sign in with a password, students open
 * their classroom. Students have no account; they join from the link their professor shares
 * (`/students/join?set=<id>` or `?taxonomy=<id>`), so the right panel takes that link, or just
 * the classroom number, and goes there.
 */

import { ArrowRight, LogIn } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  AuthBrand,
  authButtonClass,
  authFieldClass,
  authLabelClass,
  authLinkClass,
} from "@/components/auth-card";
import { QueryError } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useLogin } from "@/lib/api/queries";

/** A pasted classroom link or a bare classroom number → the join URL, or null if neither. */
export function classroomJoinPath(raw: string): string | null {
  const value = raw.trim();
  if (/^\d+$/.test(value)) return `/students/join?set=${value}`;
  try {
    const url = new URL(value, "http://placeholder.invalid");
    for (const key of ["set", "taxonomy"]) {
      const id = url.searchParams.get(key);
      if (id && /^\d+$/.test(id)) return `/students/join?${key}=${id}`;
    }
  } catch {
    // Not a URL either; fall through.
  }
  return null;
}

export function LoginScreen() {
  const router = useRouter();
  const login = useLogin();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [classroom, setClassroom] = useState("");
  const [classroomInvalid, setClassroomInvalid] = useState(false);

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

  const joinClassroom = () => {
    const path = classroomJoinPath(classroom);
    if (!path) {
      setClassroomInvalid(true);
      return;
    }
    router.push(path as Route);
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-10 px-6 py-12">
      <AuthBrand />

      <div className="grid w-full max-w-4xl overflow-hidden rounded-2xl border bg-card shadow-[var(--shadow-soft)] md:grid-cols-[1.25fr_1fr]">
        <section className="space-y-6 p-8 sm:p-10">
          <div className="space-y-1.5">
            <h1 className="font-heading font-semibold text-2xl tracking-tight">Instructors</h1>
            <p className="text-base text-muted-foreground">
              Sign in to build and review your question bank.
            </p>
          </div>
          <form
            className="space-y-5"
            onSubmit={(event) => {
              event.preventDefault();
              void submit();
            }}
          >
            <div className="space-y-2.5">
              <Label htmlFor="login-email" className={authLabelClass}>
                Email
              </Label>
              <Input
                id="login-email"
                type="email"
                autoComplete="username"
                className={authFieldClass}
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@university.edu"
              />
            </div>
            <div className="space-y-2.5">
              <div className="flex items-baseline justify-between">
                <Label htmlFor="login-password" className={authLabelClass}>
                  Password
                </Label>
                <Link href={"/forgot-password" as Route} className={authLinkClass}>
                  Forgot password?
                </Link>
              </div>
              <Input
                id="login-password"
                type="password"
                autoComplete="current-password"
                className={authFieldClass}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </div>

            {login.isError ? <QueryError error={login.error} /> : null}

            <Button
              type="submit"
              className={authButtonClass}
              disabled={!email.trim() || !password || login.isPending}
            >
              <LogIn />
              {login.isPending ? "Signing in…" : "Sign in"}
            </Button>
          </form>
          <p className="text-base text-muted-foreground">
            New here?{" "}
            <Link href={"/register" as Route} className={authLinkClass}>
              Create an account
            </Link>
          </p>
        </section>

        <section className="space-y-6 border-t bg-muted/60 p-8 sm:p-10 md:border-t-0 md:border-l">
          <div className="space-y-1.5">
            <h2 className="font-heading font-semibold text-2xl tracking-tight">Students</h2>
            <p className="text-base text-muted-foreground">
              No account needed. Open the classroom link your instructor shared, or paste it here.
            </p>
          </div>
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              joinClassroom();
            }}
          >
            <div className="space-y-2.5">
              <Label htmlFor="login-classroom" className={authLabelClass}>
                Classroom link or number
              </Label>
              <Input
                id="login-classroom"
                className={`${authFieldClass} bg-card`}
                placeholder="…/students/join?set=12"
                value={classroom}
                aria-invalid={classroomInvalid || undefined}
                onChange={(event) => {
                  setClassroom(event.target.value);
                  setClassroomInvalid(false);
                }}
              />
              {classroomInvalid ? (
                <p className="text-destructive text-sm">
                  That isn't a classroom link. Check it with your instructor.
                </p>
              ) : null}
            </div>
            <Button
              type="submit"
              variant="outline"
              className={`${authButtonClass} bg-card`}
              disabled={!classroom.trim()}
            >
              Join classroom
              <ArrowRight />
            </Button>
          </form>
        </section>
      </div>
    </div>
  );
}
