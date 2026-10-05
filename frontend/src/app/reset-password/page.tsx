import type { Metadata } from "next";
import { ResetPasswordScreen } from "./reset-password-screen";

export const metadata: Metadata = { title: "Choose a new password · Adaptive Trainer" };

/** The link in the password reset email: `/reset-password?token=…` (`app/auth/email.py`). */
export default async function ResetPasswordPage({ searchParams }: PageProps<"/reset-password">) {
  const { token } = await searchParams;
  return <ResetPasswordScreen token={typeof token === "string" ? token : ""} />;
}
