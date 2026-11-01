/**
 * The full-page card every signed-out screen uses: create an account, verify an email, forgot
 * and reset password. Sign in (`app/login`) is wider, with an instructor and a student panel,
 * but shares the logo and the sizes below. These routes render outside `AuthGate`
 * (`app-chrome.tsx`).
 */

import { LogoGlyph } from "@/components/brand-logo";

/** The logo and product name above the card. */
export function AuthBrand() {
  return (
    <span className="flex items-center gap-3.5">
      <span className="flex size-14 items-center justify-center rounded-2xl bg-primary text-primary-foreground">
        <LogoGlyph className="size-8" />
      </span>
      <span className="font-heading font-semibold text-2xl tracking-tight">Adaptive Trainer</span>
    </span>
  );
}

export function AuthCard({ subtitle, children }: { subtitle: string; children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-10 px-6 py-12">
      <AuthBrand />
      <div className="w-full max-w-md space-y-6 rounded-2xl border bg-card p-8 shadow-[var(--shadow-soft)] sm:p-10">
        <h1 className="font-heading font-semibold text-xl tracking-tight">{subtitle}</h1>
        {children}
      </div>
    </div>
  );
}

/** Matches `MIN_PASSWORD_LENGTH` in `app/auth/users.py`, which is what actually enforces it. */
export const MIN_PASSWORD_LENGTH = 12;

/** A text link on these screens ("Forgot password?", "Create an account"). */
export const authLinkClass =
  "font-medium text-base text-primary underline-offset-4 hover:underline";

/** The larger field, label and button sizes these screens use instead of the console's. */
export const authFieldClass = "h-11 px-3.5 md:text-base";
export const authLabelClass = "text-base";
export const authButtonClass = "h-11 w-full text-base";
