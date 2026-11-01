"use client";

/** The four login versions. Each keeps its own state; see `mock-login.ts` for the fake behaviour. */

import { ArrowLeft, ArrowRight, Building2, ChevronRight, Loader2, Mail, UserPlus } from "lucide-react";
import Image from "next/image";
import { useState } from "react";
import { LogoGlyph } from "@/components/brand-logo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LoginFields, linkClass } from "./login-fields";
import {
  MOCK_CLASS,
  REMEMBERED_ACCOUNTS,
  type RememberedAccount,
  useMockJoin,
  useMockLogin,
} from "./mock-login";

function Brand({ size = "md" }: { size?: "md" | "sm" }) {
  return (
    <span className="flex items-center gap-2.5">
      <span
        className={`flex items-center justify-center rounded-lg bg-primary text-primary-foreground ${
          size === "md" ? "size-9" : "size-7"
        }`}
      >
        <LogoGlyph className={size === "md" ? "size-5" : "size-4"} />
      </span>
      <span className="font-heading font-semibold tracking-tight">Adaptive Trainer</span>
    </span>
  );
}

function SignUpLine() {
  return (
    <p className="text-muted-foreground text-sm">
      New here?{" "}
      <a href="#register" className={linkClass}>
        Create an account
      </a>
    </p>
  );
}

/* ── A · Split with the product ─────────────────────────────────────────── */

export function VersionA() {
  const login = useMockLogin();
  return (
    <div className="grid min-h-[calc(100vh-57px)] lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
      <div className="flex flex-col px-6 py-8 sm:px-12">
        <Brand />
        <div className="flex flex-1 items-center">
          <div className="w-full max-w-sm space-y-6">
            <div className="space-y-1.5">
              <h1 className="font-heading font-semibold text-2xl tracking-tight">Sign in to the Studio</h1>
              <p className="text-muted-foreground text-sm">
                Students don't need an account. They join a class with a code.
              </p>
            </div>
            <LoginFields login={login} idPrefix="a" />
            <SignUpLine />
          </div>
        </div>
      </div>
      <div className="relative hidden overflow-hidden border-l bg-muted lg:flex lg:flex-col lg:justify-center lg:gap-8 lg:p-12">
        <div className="max-w-md space-y-2">
          <p className="font-medium text-primary text-sm">Review queue</p>
          <p className="font-heading font-semibold text-xl leading-snug tracking-tight">
            Every generated question waits for your verdict before a student sees it.
          </p>
        </div>
        {/* Real capture of the running app, the same one the landing page uses. */}
        <Image
          src="/landing/review-queue.png"
          alt="The review queue in the Instructor Studio"
          width={1600}
          height={1000}
          className="w-[135%] max-w-none rounded-xl border shadow-[var(--shadow-panel)]"
          priority
        />
      </div>
    </div>
  );
}

/* ── B · Instructor / student fork ──────────────────────────────────────── */

export function VersionB() {
  const login = useMockLogin();
  const join = useMockJoin();
  return (
    <div className="flex min-h-[calc(100vh-57px)] flex-col items-center justify-center gap-8 px-6 py-10">
      <Brand />
      <div className="grid w-full max-w-3xl overflow-hidden rounded-2xl border bg-card shadow-[var(--shadow-soft)] md:grid-cols-[1.25fr_1fr]">
        <section className="space-y-5 p-7 sm:p-8">
          <div className="space-y-1">
            <h1 className="font-heading font-semibold text-xl tracking-tight">Instructors</h1>
            <p className="text-muted-foreground text-sm">Sign in to build and review your question bank.</p>
          </div>
          <LoginFields login={login} idPrefix="b" />
          <SignUpLine />
        </section>
        <section className="space-y-5 border-t bg-muted/60 p-7 sm:p-8 md:border-t-0 md:border-l">
          <div className="space-y-1">
            <h2 className="font-heading font-semibold text-xl tracking-tight">Students</h2>
            <p className="text-muted-foreground text-sm">No account needed. Enter the code your instructor gave you.</p>
          </div>
          {join.status === "done" ? (
            <div className="space-y-1 rounded-lg border bg-card p-4">
              <p className="text-muted-foreground text-xs">Joining</p>
              <p className="font-medium">{MOCK_CLASS.name}</p>
              <p className="text-muted-foreground text-sm">{MOCK_CLASS.instructor}</p>
            </div>
          ) : (
            <form
              className="space-y-3"
              onSubmit={(event) => {
                event.preventDefault();
                join.submit();
              }}
            >
              <div className="space-y-2">
                <Label htmlFor="b-code">Class code</Label>
                <Input
                  id="b-code"
                  placeholder="PY-4821"
                  className="font-mono uppercase tracking-widest"
                  value={join.code}
                  aria-invalid={join.status === "error" || undefined}
                  onChange={(event) => join.setCode(event.target.value)}
                />
                {join.status === "error" ? (
                  <p className="text-destructive text-sm">No class with that code. Check it with your instructor.</p>
                ) : null}
              </div>
              <Button type="submit" variant="outline" className="w-full bg-card" disabled={!join.code.trim()}>
                {join.status === "pending" ? <Loader2 className="animate-spin" /> : null}
                Join class
                <ArrowRight />
              </Button>
            </form>
          )}
        </section>
      </div>
    </div>
  );
}

/* ── C · Account picker ─────────────────────────────────────────────────── */

export function VersionC() {
  const [picked, setPicked] = useState<RememberedAccount | "other" | null>(null);
  return (
    <div className="flex min-h-[calc(100vh-57px)] items-center justify-center px-6 py-10">
      <div className="w-full max-w-md space-y-6">
        <div className="flex justify-center">
          <Brand />
        </div>
        <div className="rounded-2xl border bg-card p-6 shadow-[var(--shadow-soft)] sm:p-7">
          {picked === null ? (
            <AccountList onPick={setPicked} />
          ) : (
            <PasswordStep key={picked === "other" ? "other" : picked.email} picked={picked} onBack={() => setPicked(null)} />
          )}
        </div>
        <p className="text-center text-muted-foreground text-xs">
          A student?{" "}
          <a href="#join" className="font-medium text-primary underline-offset-4 hover:underline">
            Join with a class code
          </a>
        </p>
      </div>
    </div>
  );
}

function AccountList({ onPick }: { onPick: (pick: RememberedAccount | "other") => void }) {
  return (
    <div className="space-y-5">
      <div className="space-y-1">
        <h1 className="font-heading font-semibold text-xl tracking-tight">Welcome back</h1>
        <p className="text-muted-foreground text-sm">Choose an account to continue.</p>
      </div>
      <ul className="-mx-2 space-y-1">
        {REMEMBERED_ACCOUNTS.map((account) => (
          <li key={account.email}>
            <button
              type="button"
              onClick={() => onPick(account)}
              className="flex w-full items-center gap-3 rounded-lg px-2 py-2.5 text-left transition-colors hover:bg-muted"
            >
              <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-accent font-medium text-accent-foreground text-sm">
                {account.initials}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium text-sm">{account.email}</span>
                <span className="block truncate text-muted-foreground text-xs">
                  {account.lastCourse} · {account.lastSeen}
                </span>
              </span>
              <ChevronRight className="size-4 text-muted-foreground" />
            </button>
          </li>
        ))}
        <li>
          <button
            type="button"
            onClick={() => onPick("other")}
            className="flex w-full items-center gap-3 rounded-lg px-2 py-2.5 text-left transition-colors hover:bg-muted"
          >
            <span className="flex size-10 shrink-0 items-center justify-center rounded-full border border-dashed text-muted-foreground">
              <UserPlus className="size-4" />
            </span>
            <span className="flex-1 font-medium text-sm">Use another account</span>
          </button>
        </li>
      </ul>
      <div className="border-t pt-4">
        <SignUpLine />
      </div>
    </div>
  );
}

function PasswordStep({ picked, onBack }: { picked: RememberedAccount | "other"; onBack: () => void }) {
  const login = useMockLogin(picked === "other" ? "" : picked.email);
  return (
    <div className="space-y-5">
      <button
        type="button"
        onClick={onBack}
        className="-ml-1 flex items-center gap-1 text-muted-foreground text-sm hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        All accounts
      </button>
      {picked === "other" ? (
        <h1 className="font-heading font-semibold text-xl tracking-tight">Sign in</h1>
      ) : (
        <div className="flex items-center gap-3">
          <span className="flex size-11 items-center justify-center rounded-full bg-accent font-medium text-accent-foreground">
            {picked.initials}
          </span>
          <div className="min-w-0">
            <p className="font-medium">{picked.name}</p>
            <p className="truncate text-muted-foreground text-sm">{picked.email}</p>
          </div>
        </div>
      )}
      <LoginFields
        login={login}
        idPrefix="c"
        hideEmail={picked !== "other"}
        autoFocusPassword={picked !== "other"}
        submitLabel="Continue"
      />
    </div>
  );
}

/* ── D · Quiet, with SSO and email link ─────────────────────────────────── */

export function VersionD() {
  const login = useMockLogin();
  const [linkSent, setLinkSent] = useState(false);
  return (
    <div className="flex min-h-[calc(100vh-57px)] flex-col px-6 py-8 sm:px-12">
      <Brand size="sm" />
      <div className="flex flex-1 items-center justify-center">
        <div className="w-full max-w-[22rem] space-y-7">
          <div className="space-y-2">
            <h1 className="font-bold font-heading text-3xl tracking-tight">Sign in</h1>
            <p className="text-muted-foreground">Instructor Studio</p>
          </div>
          <div className="space-y-2.5">
            {/* TODO(real): no SSO or email-link sign-in exists in the backend (app/auth). */}
            <Button variant="outline" className="h-10 w-full justify-start gap-3 bg-card">
              <Building2 />
              Continue with University of Nevada, Reno
            </Button>
            <Button
              variant="outline"
              className="h-10 w-full justify-start gap-3 bg-card"
              onClick={() =>
                login.email.trim() ? setLinkSent(true) : document.getElementById("d-email")?.focus()
              }
            >
              <Mail />
              {linkSent ? `Link sent to ${login.email}` : "Email me a sign-in link"}
            </Button>
          </div>
          <div className="flex items-center gap-3 text-muted-foreground text-xs">
            <span className="h-px flex-1 bg-border" />
            or use your password
            <span className="h-px flex-1 bg-border" />
          </div>
          <LoginFields login={login} idPrefix="d" />
          <SignUpLine />
        </div>
      </div>
      <p className="text-center text-muted-foreground text-xs">
        Students join with a class code from their instructor.
      </p>
    </div>
  );
}
