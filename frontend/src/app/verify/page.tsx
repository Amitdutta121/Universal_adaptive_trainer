import type { Metadata } from "next";
import { VerifyScreen } from "./verify-screen";

export const metadata: Metadata = { title: "Verify your email · Adaptive Trainer" };

/** The link in the verification email: `/verify?token=…` (`app/auth/email.py`). */
export default async function VerifyPage({ searchParams }: PageProps<"/verify">) {
  const { token } = await searchParams;
  return <VerifyScreen token={typeof token === "string" ? token : ""} />;
}
