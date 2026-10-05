/**
 * The full-page card every signed-out screen uses: sign in, create an account, verify an
 * email, forgot and reset password. These routes render outside `AuthGate` (`app-chrome.tsx`).
 */

import { Sparkles } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function AuthCard({ subtitle, children }: { subtitle: string; children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <Card className="w-full max-w-sm border-border/70">
        <CardHeader className="items-center gap-2 text-center">
          <span className="flex size-10 items-center justify-center rounded-full bg-primary/10 text-primary">
            <Sparkles className="size-5" />
          </span>
          <CardTitle className="text-xl">Adaptive Trainer</CardTitle>
          <p className="text-muted-foreground text-sm">{subtitle}</p>
        </CardHeader>
        <CardContent className="space-y-4">{children}</CardContent>
      </Card>
    </div>
  );
}

/** Matches `MIN_PASSWORD_LENGTH` in `app/auth/users.py`, which is what actually enforces it. */
export const MIN_PASSWORD_LENGTH = 12;

/** A text link on these screens ("Forgot password?", "Create an account"). */
export const authLinkClass = "font-medium text-primary text-sm underline-offset-4 hover:underline";
