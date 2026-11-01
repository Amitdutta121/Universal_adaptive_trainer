/**
 * The style library grouped by what the student has to be able to do, so the setup modal can
 * show every subtopic the same library in the same places.
 *
 * The group follows from a style's question type: the library has no separate field for it.
 * A type with no group here lands in "Other questions" rather than disappearing.
 */

import type { RegistryQuestionType } from "@/lib/question-types/registry";

export interface StyleGroup {
  /** The standard name for this kind of question in CS education. */
  title: string;
  /** One sentence on what the student does, so the title needs no glossary. */
  description: string;
  types: readonly RegistryQuestionType[];
}

/** In teaching order: understanding first, writing code last. */
export const STYLE_GROUPS: readonly StyleGroup[] = [
  {
    title: "Concept questions",
    description: "Students choose the correct statement about an idea.",
    types: ["multiple_choice", "true_false"],
  },
  {
    title: "Code tracing",
    description: "Students read code and predict exactly what it prints.",
    types: ["output_prediction"],
  },
  {
    title: "Code completion",
    description: "Students fill in or reorder lines of code they are given.",
    types: ["code_completion", "parsons"],
  },
  {
    title: "Debugging",
    description: "Students find and fix the error in code they are given.",
    types: ["debugging"],
  },
  {
    title: "Code writing",
    description: "Students write a working function from a short description.",
    types: ["coding"],
  },
  {
    title: "Calculation",
    description: "Students work out a numeric value or an expression.",
    types: ["numeric_response", "equation_response"],
  },
];

const OTHER = { title: "Other questions", description: "Styles of any other question type." };

/**
 * The library's styles split into groups, in group order, each keeping library order. Empty
 * groups are left out. The result depends only on the library, never on a subtopic.
 */
export function groupStyles<T extends { question_type: string }>(
  library: readonly T[],
): { title: string; description: string; styles: T[] }[] {
  const known = new Set<string>(STYLE_GROUPS.flatMap((group) => group.types));
  const groups = STYLE_GROUPS.map((group) => ({
    title: group.title,
    description: group.description,
    styles: library.filter((style) =>
      (group.types as readonly string[]).includes(style.question_type),
    ),
  }));
  groups.push({
    ...OTHER,
    styles: library.filter((style) => !known.has(style.question_type)),
  });
  return groups.filter((group) => group.styles.length > 0);
}
