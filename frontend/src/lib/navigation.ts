/**
 * The professor-facing navigation, mirroring `app/web/navigation.py`.
 *
 * Single source of truth on this side: the sidebar and the dashboard cards both read
 * this list, so a section cannot appear in one place and be missing from another.
 *
 * The keys match `NAV_SECTIONS` on the backend, with one addition: `review`. The
 * Jinja UI reaches the review queue from inside the questions page, but it is the
 * screen a professor opens most, so here it is a section of its own.
 */

import {
  BookOpen,
  ClipboardCheck,
  GraduationCap,
  Grid3x3,
  ListChecks,
  type LucideIcon,
  MessageSquareText,
  Network,
  Scale,
  ScrollText,
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
    key: "review",
    label: "Review Queue",
    path: "/review",
    summary: "Questions that passed validation and are waiting for a professor verdict.",
    icon: ClipboardCheck,
  },
  {
    key: "feedback",
    label: "Professor Feedback",
    path: "/feedback",
    summary: "The approve / reject / edit history that teaches the generator your preferences.",
    icon: MessageSquareText,
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
