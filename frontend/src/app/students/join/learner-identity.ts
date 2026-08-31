/**
 * Per-browser learner identity for the anonymous student flow (ADR-041).
 *
 * Students have no accounts, so the only thing that lets a returning browser be
 * recognised is the `resume_token` the backend minted when it enrolled. We keep
 * that token here, alongside the student id and the name and email last used, so
 * the join screen can offer "resume" instead of forcing a re-enrol that the
 * unique-name rule would reject.
 *
 * This is browser-local convenience state: it never leaves the device, may come
 * back empty (private window, cleared storage, a different browser), and every
 * access is wrapped so a storage exception cannot break the page.
 */

const IDENTITY_KEY = "adaptive-trainer:learner-identity";

// Predates the token: earlier builds stored just the name here for prefill. Still
// read as a fallback, and kept in sync on save, so nothing regresses for a
// browser that only has the old key.
const LEGACY_NAME_KEY = "adaptive-trainer:learner-name";

export interface LearnerIdentity {
  studentId: number;
  resumeToken: string;
  displayName: string;
  email: string;
}

function isIdentity(value: unknown): value is LearnerIdentity {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as LearnerIdentity).studentId === "number" &&
    typeof (value as LearnerIdentity).resumeToken === "string" &&
    typeof (value as LearnerIdentity).displayName === "string" &&
    typeof (value as LearnerIdentity).email === "string" &&
    (value as LearnerIdentity).resumeToken.length > 0
  );
}

/** The stored identity for this browser, or `null` if there is none / it is unusable. */
export function loadLearnerIdentity(): LearnerIdentity | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(IDENTITY_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    return isIdentity(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

/** Persist the identity once an enrol or resume has actually succeeded. */
export function saveLearnerIdentity(identity: LearnerIdentity): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(IDENTITY_KEY, JSON.stringify(identity));
    window.localStorage.setItem(LEGACY_NAME_KEY, identity.displayName);
  } catch {
    // A browser that refuses storage just loses the resume convenience.
  }
}

/** Drop the stored identity — a stale token, or the learner asking to switch. */
export function clearLearnerIdentity(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(IDENTITY_KEY);
    window.localStorage.removeItem(LEGACY_NAME_KEY);
  } catch {
    // Nothing to recover from here.
  }
}

/** A name to prefill the enrol field with, from the identity or the legacy key. */
export function rememberedLearnerName(): string {
  const identity = loadLearnerIdentity();
  if (identity) return identity.displayName;
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(LEGACY_NAME_KEY) ?? "";
  } catch {
    return "";
  }
}

/** An email to prefill the enrol field with. Only the identity blob carries one. */
export function rememberedLearnerEmail(): string {
  return loadLearnerIdentity()?.email ?? "";
}
