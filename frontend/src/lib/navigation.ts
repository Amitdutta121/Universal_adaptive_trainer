/**
 * The professor-facing navigation.
 *
 * Single source of truth on this side: the sidebar and the dashboard cards both
 * read this list, so a section cannot appear in one place and be missing from
 * another.
 *
 * `review` and `generate` are distinct routes because they are screens of their
 * own in the React console, even though their data hangs off the questions API.
 *
 * Every `path` is relative to the open course: the sidebar and dashboard turn
 * `/books` into `/courses/{id}/books` with `coursePath` (`lib/course.ts`).
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
  Users,
  Wand2,
} from "lucide-react";

/** A sidebar-only sub-link, nested under a `NavSection` that has more than one screen. */
export interface NavChild {
  key: string;
  label: string;
  /** Relative to the open course. */
  path: string;
}

export interface NavSection {
  key: string;
  label: string;
  /** Relative to the open course, e.g. `/books`. */
  path: string;
  summary: string;
  icon: LucideIcon;
  /**
   * Sub-screens under one nav item, rendered as a collapsible group in the
   * sidebar. Dashboard cards (`app/page.tsx`) read only `label`/`path`/
   * `summary`/`icon`, so a section keeps a working dashboard card whether or
   * not it has children.
   */
  children?: readonly NavChild[];
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
    summary:
      "Build a Topic → Subtopic taxonomy, or import one you already have. Every page follows the taxonomy chosen at the top right.",
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
    summary: "Generate one question at a time from a chunk, or produce a whole sheet in bulk.",
    icon: Wand2,
    children: [
      {
        key: "generate-single",
        label: "Generate questions",
        path: "/questions/generate/single",
      },
      {
        key: "generate-bulk",
        label: "Bulk generate",
        path: "/questions/generate",
      },
    ],
  },
  {
    key: "review",
    label: "Review Queue",
    path: "/review",
    summary:
      "Professor feedback now lives here: review, approve, reject, or edit queued questions.",
    icon: ClipboardCheck,
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
    key: "classrooms",
    label: "Classrooms",
    path: "/students",
    summary: "Generate joinable adaptive-training classrooms from frozen question sets.",
    icon: GraduationCap,
  },
  {
    key: "roster",
    label: "Roster",
    path: "/students/roster",
    summary: "Enrolled learners' progress: score trends, BKT topic mastery, and subtopic weakness.",
    icon: Users,
  },
] as const;

export const SECTIONS_BY_KEY: Record<string, NavSection> = Object.fromEntries(
  NAV_SECTIONS.map((section) => [section.key, section]),
);
