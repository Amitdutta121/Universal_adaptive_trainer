/**
 * Stand-in data for the course-capabilities prototypes. The only fake data in this folder.
 *
 * TODO(real): the registry below (capabilities, question types, subject presets) becomes code in
 * the planned `graders/` package (G0/G1), and a course's enabled set becomes a stored course
 * setting (G3). Nothing here is read from or saved to the API.
 *
 * The model, as designed:
 * - A **capability** is a checking ability, implemented by a versioned grader.
 * - A **question type** fixes the answer format (widget). It is gradable by any one of its
 *   `gradedBy` capabilities and also needs every capability in `alsoNeeds` (for example, the
 *   Python runner to prove an output-prediction answer when the question is created).
 * - A **course** enables capabilities, starting from a subject preset. Its allowed question types
 *   are derived: every type with at least one enabled `gradedBy` and all of `alsoNeeds` enabled,
 *   minus any type the professor switched off.
 */

export type CapabilityFamily = "structured" | "text" | "quantitative" | "code" | "semantic";

export interface Capability {
  id: string;
  label: string;
  family: CapabilityFamily;
  /** What it can check, in the words the taxonomy drafter and question generator are given. */
  card: string;
  /** False for LLM grading: its scores never count toward mastery. */
  deterministic: boolean;
  /** "planned" means no grader exists yet, so it cannot be enabled. */
  status: "available" | "planned";
  /** The grader that implements it, once built. */
  grader: string | null;
  /** A one-line example of a question it grades. */
  example: string;
}

export interface QuestionType {
  id: string;
  label: string;
  /** The answer widget the student sees. */
  widget: string;
  /** Any one of these, enabled, can grade it. */
  gradedBy: readonly string[];
  /** All of these must also be enabled (checks at creation time). */
  alsoNeeds: readonly string[];
}

export interface SubjectPreset {
  id: string;
  label: string;
  blurb: string;
  capabilities: readonly string[];
}

export const FAMILY_LABEL: Record<CapabilityFamily, string> = {
  structured: "Structured answers",
  text: "Text",
  quantitative: "Numbers and maths",
  code: "Code",
  semantic: "Written answers (AI-graded)",
};

export const CAPABILITIES: readonly Capability[] = [
  {
    id: "structured.choice",
    label: "Choice",
    family: "structured",
    card: "Checks which option was picked: one right answer, or a set of right answers.",
    deterministic: true,
    status: "available",
    grader: "answer_matcher@1",
    example: "Which of these is a mutable type? (a) tuple (b) list (c) str",
  },
  {
    id: "structured.ordering",
    label: "Ordering",
    family: "structured",
    card: "Checks the order of given pieces, optionally with their indentation.",
    deterministic: true,
    status: "available",
    grader: "answer_matcher@1",
    example: "Put these lines in order so the loop prints 1 to 5.",
  },
  {
    id: "text.normalized_match",
    label: "Exact text",
    family: "text",
    card: "Checks text against an expected answer after normalising case, spacing and line endings.",
    deterministic: true,
    status: "available",
    grader: "answer_matcher@1",
    example: "What does print(len('abc')) output?",
  },
  {
    id: "quantity.units",
    label: "Numeric with units",
    family: "quantitative",
    card: "Checks a number within a tolerance, converting between compatible units.",
    deterministic: true,
    status: "planned",
    grader: null,
    example: "A ball falls from rest. Its speed after 2 s, in m/s?",
  },
  {
    id: "symbolic.expression_equivalence",
    label: "Equation / expression",
    family: "quantitative",
    card: "Checks that a formula is mathematically equivalent to the expected one.",
    deterministic: true,
    status: "planned",
    grader: null,
    example: "Differentiate x² sin x.",
  },
  {
    id: "code.python.execute",
    label: "Run Python",
    family: "code",
    card: "Runs Python and captures its output and errors; used to prove answers when a question is created.",
    deterministic: true,
    status: "available",
    grader: "python_runner@1",
    example: "(used behind output-prediction and code questions)",
  },
  {
    id: "code.python.tests",
    label: "Python tests",
    family: "code",
    card: "Runs a student's Python against hidden tests (input, expected output, asserts); partial credit per test.",
    deterministic: true,
    status: "available",
    grader: "python_tests@1",
    example: "Write factorial(n). 4 of 5 tests passing scores 80.",
  },
  {
    id: "semantic.source_grounded",
    label: "Rubric-graded explanation",
    family: "semantic",
    card: "An AI grades a short written answer against a rubric and the course's reading.",
    deterministic: false,
    status: "available",
    grader: "llm_rubric@1",
    example: "Explain in two sentences why the loop never ends.",
  },
];

export const QUESTION_TYPES: readonly QuestionType[] = [
  { id: "multiple_choice", label: "Multiple choice", widget: "Choice buttons", gradedBy: ["structured.choice"], alsoNeeds: [] },
  { id: "true_false", label: "True / false", widget: "Two buttons", gradedBy: ["structured.choice"], alsoNeeds: [] },
  { id: "parsons", label: "Parsons (order the code)", widget: "Drag to order", gradedBy: ["structured.ordering"], alsoNeeds: ["code.python.execute"] },
  { id: "output_prediction", label: "Output prediction", widget: "Text box", gradedBy: ["text.normalized_match"], alsoNeeds: ["code.python.execute"] },
  { id: "code_completion", label: "Code completion", widget: "Code editor", gradedBy: ["code.python.tests"], alsoNeeds: ["code.python.execute"] },
  { id: "debugging", label: "Debugging", widget: "Code editor", gradedBy: ["code.python.tests"], alsoNeeds: ["code.python.execute"] },
  { id: "coding", label: "Coding", widget: "Code editor", gradedBy: ["code.python.tests"], alsoNeeds: ["code.python.execute"] },
  { id: "short_answer", label: "Short answer", widget: "Text box", gradedBy: ["text.normalized_match", "quantity.units", "symbolic.expression_equivalence"], alsoNeeds: [] },
  { id: "numeric_response", label: "Numeric response", widget: "Number + unit", gradedBy: ["quantity.units"], alsoNeeds: [] },
  { id: "equation_response", label: "Equation response", widget: "Maths input", gradedBy: ["symbolic.expression_equivalence"], alsoNeeds: [] },
  { id: "short_explanation", label: "Short explanation", widget: "Paragraph box", gradedBy: ["semantic.source_grounded"], alsoNeeds: [] },
];

export const SUBJECT_PRESETS: readonly SubjectPreset[] = [
  {
    id: "intro_python",
    label: "Intro programming (Python)",
    blurb: "Choice, Parsons, output prediction and code questions, graded by running Python.",
    capabilities: ["structured.choice", "structured.ordering", "text.normalized_match", "code.python.execute", "code.python.tests"],
  },
  {
    id: "physics",
    label: "Physics",
    blurb: "Conceptual choice plus numeric and equation answers.",
    capabilities: ["structured.choice", "quantity.units", "symbolic.expression_equivalence"],
  },
  {
    id: "biology",
    label: "Biology",
    blurb: "Conceptual choice and exact short answers.",
    capabilities: ["structured.choice", "text.normalized_match"],
  },
  {
    id: "custom",
    label: "Something else",
    blurb: "Start from choice questions and add what your course needs.",
    capabilities: ["structured.choice"],
  },
];

export const CAPABILITIES_BY_ID: Record<string, Capability> = Object.fromEntries(
  CAPABILITIES.map((capability) => [capability.id, capability]),
);

/** Why a question type is or is not allowed, given the enabled capabilities. */
export interface TypeAvailability {
  type: QuestionType;
  /** Gradable and every requirement met (before the professor's own switch-off). */
  possible: boolean;
  /** Possible and not switched off by the professor. */
  allowed: boolean;
  /** Enabled capabilities that can grade it. */
  gradedByEnabled: string[];
  /** What would have to be enabled for it to become possible. */
  missing: string[];
}

export function typeAvailability(
  enabled: ReadonlySet<string>,
  switchedOff: ReadonlySet<string> = new Set(),
): TypeAvailability[] {
  return QUESTION_TYPES.map((type) => {
    const gradedByEnabled = type.gradedBy.filter((id) => enabled.has(id));
    const missingNeeds = type.alsoNeeds.filter((id) => !enabled.has(id));
    const missing = [
      ...(gradedByEnabled.length === 0 ? [type.gradedBy[0] as string] : []),
      ...missingNeeds,
    ];
    const possible = missing.length === 0;
    return {
      type,
      possible,
      allowed: possible && !switchedOff.has(type.id),
      gradedByEnabled,
      missing,
    };
  });
}

/** Capabilities that cannot be enabled yet, because no grader exists. */
export function isSelectable(capability: Capability): boolean {
  return capability.status === "available";
}
