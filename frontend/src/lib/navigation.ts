/**
 * The professor-facing navigation.
 *
 * Single source of truth on this side: the sidebar and the dashboard cards both
 * read this list, so a section cannot appear in one place and be missing from
 * another.
 *
 * `review` and `generate` are distinct routes because they are screens of their
 * own in the React console, even though their data hangs off the questions API.
 */

import {
  BookOpen,
  ClipboardCheck,
  GraduationCap,
  Grid3x3,
  ListChecks,
  type LucideIcon,
  Network,
  Scale,
  ScrollText,
  Wand2,
} from "lucide-react";
import type { Route } from "next";

export interface NavSection {
  key: string;
  label: string;
  /** `Route` is Next's typed-routes union: a path with no page fails to compile. */
  path: Route;
  summary: string;
  icon: LucideIcon;
}

export const NAV_SECTIONS: readonly NavSection[] = [
  {
    key: "books",
    label: "Books",
    path: "/books",
    summary: "Upload introductory Python textbooks and inspect their extracted structure.",
    icon: BookOpen,
  },
  {
    key: "curriculum",
    label: "Curriculum",
    path: "/curriculum",
    summary: "Upload a fixed Topic → Subtopic taxonomy JSON for adaptive training.",
    icon: Network,
  },
  {
    key: "questions",
    label: "Questions",
    path: "/questions",
    summary: "Generate, validate and review Python assessment questions.",
    icon: ListChecks,
  },
  {
    key: "generate",
    label: "Generate",
    path: "/questions/generate",
    summary: "Set what each book chunk should produce, then generate the whole sheet at once.",
    icon: Wand2,
  },
  {
    key: "review",
    label: "Review Queue",
    path: "/review",
    summary: "Professor feedback now lives here: review, approve, reject, or edit queued questions.",
    icon: ClipboardCheck,
  },
  {
    key: "instructions",
    label: "Instructions",
    path: "/instructions",
    summary: "What the generator is told for each question type, learned from your reviews.",
    icon: ScrollText,
  },
  {
    key: "judges",
    label: "Judges",
    path: "/judges",
    summary: "The four advisory reviewers, and the prompt each one follows.",
    icon: Scale,
  },
  {
    key: "coverage",
    label: "Coverage",
    path: "/coverage",
    summary: "Whether the approved questions cover every subtopic at every difficulty.",
    icon: Grid3x3,
  },
  {
    key: "students",
    label: "Students",
    path: "/students",
    summary: "Adaptive training progress: BKT topic mastery and subtopic weakness.",
    icon: GraduationCap,
  },
] as const;

export const SECTIONS_BY_KEY: Record<string, NavSection> = Object.fromEntries(
  NAV_SECTIONS.map((section) => [section.key, section]),
);
