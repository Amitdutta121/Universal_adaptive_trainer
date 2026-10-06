import type { Metadata } from "next";
import { RegisterScreen } from "./register-screen";

export const metadata: Metadata = { title: "Create an account · Adaptive Trainer" };

export default function RegisterPage() {
  return <RegisterScreen />;
}
