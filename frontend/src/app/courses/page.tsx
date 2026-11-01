import type { Metadata } from "next";
import { CoursesScreen } from "./courses-screen";

export const metadata: Metadata = { title: "Courses · Adaptive Trainer" };

export default function CoursesPage() {
  return <CoursesScreen />;
}
