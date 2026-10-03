/**
 * Shapes shared by the question-setup prototype. Everything in `mock-*.ts` is stand-in data:
 * nothing here is read from or written to the API, and no LLM is called.
 *
 * The model, as designed:
 * - **Mining** reads the uploaded book's table of contents, picks the practice sections, and
 *   classifies the exercises it finds (type of task, difficulty, chapter).
 * - A **template** (a "question style") is a reusable pattern the generator can apply across
 *   subtopics: one question type, one difficulty, one way of asking. The professor approves or
 *   skips it by looking at two example questions written from it.
 * - The **plan** is the blueprint: approved subtopic x difficulty cells, the floor per cell the
 *   adaptive engine needs, and which approved templates fill each gap.
 */

export type Difficulty = "easy" | "medium" | "hard";

export const DIFFICULTIES: readonly Difficulty[] = ["easy", "medium", "hard"];

export const DIFFICULTY_LABEL: Record<Difficulty, string> = {
  easy: "Easy",
  medium: "Medium",
  hard: "Hard",
};

/** One example question shown on a template card. The professor sees the answer key. */
export interface ExampleQuestion {
  prompt: string;
  /** A code listing shown under the prompt. */
  code?: string;
  /** Choice options; `correct` marks the key. */
  options?: readonly { text: string; correct?: boolean }[];
  /** Parsons: the solution lines in their correct order (shown shuffled to the student). */
  lines?: readonly string[];
  /** The answer key in words: expected output, value with unit, expression, accepted text. */
  answer?: string;
  /** Hidden test count, for code types graded by tests. */
  tests?: number;
  /** The book section the example is grounded in. */
  grounding: string;
}

export interface Template {
  id: string;
  /** Short imperative name of the pattern, as a professor would say it. */
  name: string;
  /** One sentence on what the student does and what it checks. */
  summary: string;
  questionType: string;
  difficulty: Difficulty;
  /** How the answer is checked, in plain words. */
  checkedBy: string;
  /** Why the AI suggests it: what in the book looks like this. */
  evidence: string;
  /** Topic ids this pattern cannot be used for, with the reason shown in the plan. */
  excludeTopics?: readonly string[];
  excludeReason?: string;
  examples: readonly [ExampleQuestion, ExampleQuestion];
}

export interface MinedSection {
  title: string;
  /** How many sections in the book carry this heading. */
  count: number;
  kind: "exercises" | "conceptual" | "review" | "objectives" | "answers";
}

export interface MinedItem {
  text: string;
  source: string;
  inferredType: string;
  difficulty: Difficulty;
}

export interface Subtopic {
  id: string;
  name: string;
  /** Approved questions already in the bank, per difficulty. */
  have: Record<Difficulty, number>;
}

export interface Topic {
  id: string;
  name: string;
  subtopics: readonly Subtopic[];
}

export interface Domain {
  id: string;
  /** Subject preset label, as `app/assessment/catalog.py` names it. */
  subjectLabel: string;
  course: string;
  book: { title: string; author: string; pages: number; chapters: number; sections: number };
  taxonomy: { label: string; topics: number; subtopics: number };
  /** Question types the course has enabled, as display labels keyed by type id. */
  questionTypes: Record<string, string>;
  mining: {
    tocTokens: number;
    sectionsRouted: number;
    sections: readonly MinedSection[];
    itemsFound: number;
    level: string;
    /** Share of mined items per kind of task, as the analysis call labelled them. */
    taskMix: readonly { label: string; share: number }[];
    difficultyMix: Record<Difficulty, number>;
    samples: readonly MinedItem[];
    notes: readonly string[];
  };
  /** Things the professor can ask for before suggestions are drawn. */
  wishes: readonly string[];
  templates: readonly Template[];
  /** Shown only if a difficulty column ends the deck with nothing approved. */
  reserve: readonly Template[];
  topics: readonly Topic[];
}

export const SKIP_REASONS = [
  "Not this kind of question",
  "Too easy",
  "Too hard",
  "Wrong or unclear",
  "Not in my course",
] as const;

export type SkipReason = (typeof SKIP_REASONS)[number];
