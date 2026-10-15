import type { Metadata } from "next";
import { SettingsScreen } from "./settings-screen";

export const metadata: Metadata = { title: "Model settings · Adaptive Trainer" };

export default function SettingsPage() {
  return <SettingsScreen />;
}
