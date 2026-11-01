/**
 * Mock data and a fake sign-in for the login prototypes. Nothing here calls the API.
 *
 * Behaviour, the same in every version:
 * - password `wrong` → "wrong email or password" (after 3 tries it warns about the lockout)
 * - any other non-empty password → a short pending state, then "signed in"
 * - class code `PY-4821` is valid; anything else is "no class with that code"
 */

import { useState } from "react";

/** TODO(real): there is no "remembered accounts" store; the real app only has a session cookie. */
export const REMEMBERED_ACCOUNTS = [
  {
    name: "Dana Okafor",
    email: "dana.okafor@unr.edu",
    initials: "DO",
    lastCourse: "CS 135 · Intro to Python",
    lastSeen: "2 days ago",
  },
  {
    name: "Dana Okafor",
    email: "dokafor@tmcc.edu",
    initials: "DO",
    lastCourse: "STAT 152 · Intro to Statistics",
    lastSeen: "3 weeks ago",
  },
] as const;

export type RememberedAccount = (typeof REMEMBERED_ACCOUNTS)[number];

/** TODO(real): the class join flow takes a code, but this one is invented. */
export const VALID_CLASS_CODE = "PY-4821";
export const MOCK_CLASS = { code: VALID_CLASS_CODE, name: "CS 135 · Intro to Python", instructor: "Dr. Okafor" };

const MAX_ATTEMPTS = 5;

export function useMockLogin(initialEmail = "") {
  const [email, setEmail] = useState(initialEmail);
  const [password, setPassword] = useState("");
  const [attempts, setAttempts] = useState(0);
  const [status, setStatus] = useState<"idle" | "pending" | "error" | "done">("idle");

  const canSubmit = email.trim().length > 0 && password.length > 0 && status !== "pending";

  const submit = () => {
    if (!canSubmit) return;
    setStatus("pending");
    window.setTimeout(() => {
      if (password === "wrong") {
        setAttempts((n) => n + 1);
        setPassword("");
        setStatus("error");
      } else {
        setStatus("done");
      }
    }, 700);
  };

  const errorText =
    status !== "error"
      ? null
      : attempts >= 3
        ? `${attempts} failed attempts. After ${MAX_ATTEMPTS}, sign-in is paused for 15 minutes.`
        : "Check both and try again, or reset your password.";

  return { email, setEmail, password, setPassword, status, canSubmit, submit, errorText };
}

export type MockLogin = ReturnType<typeof useMockLogin>;

export function useMockJoin() {
  const [code, setCode] = useState("");
  const [status, setStatus] = useState<"idle" | "pending" | "error" | "done">("idle");
  const submit = () => {
    if (!code.trim() || status === "pending") return;
    setStatus("pending");
    window.setTimeout(() => {
      setStatus(code.trim().toUpperCase() === VALID_CLASS_CODE ? "done" : "error");
    }, 600);
  };
  return { code, setCode, status, submit };
}
