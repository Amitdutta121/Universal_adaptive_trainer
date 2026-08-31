/**
 * Mock data and pure logic for the student-experience design prototype.
 *
 * This file has NO backend and NO LLM calls. It stands in for four things the
 * real app gets from the API (see `student-session-screen.tsx`):
 *
 *  - a frozen question set to practise against,
 *  - the adaptive selection that picks the next question from your measured
 *    weak spots (`selectNextQuestion`),
 *  - answer scoring, including partial credit (`scoreAnswer`),
 *  - the mastery/weakness shift each answer causes (`applyOutcome`).
 *
 * Everything here is deterministic — a small seeded PRNG stands in for the
 * randomness in the real weakness-weighted roulette, so the same session seed
 * always produces the same run. Replace this module with the typed query layer
 * when porting the design into the console.
 */

export type QuestionType =
  | "multiple_choice"
  | "true_false"
  | "short_text"
  | "output_prediction"
  | "parsons";

export type Difficulty = "easy" | "medium" | "hard";

export type ParsonsStep = { id: string; text: string };

export type Question = {
  id: string;
  topicId: string;
  topicName: string;
  subtopicId: string;
  subtopicName: string;
  difficulty: Difficulty;
  type: QuestionType;
  prompt: string;
  /** Read-only reference code shown above the answer input. */
  code?: string;
  /** multiple_choice */
  options?: string[];
  correctOptionIndex?: number;
  /** true_false */
  correctBoolean?: boolean;
  /** short_text + output_prediction — any one is a full-credit match. */
  acceptableAnswers?: string[];
  /** parsons — the steps in their correct order. */
  steps?: ParsonsStep[];
  /** Shown in the "what was correct" review after answering. */
  explanation: string;
  feedbackCorrect: string;
  feedbackPartial?: string;
  feedbackIncorrect: string;
};

export type PracticeSet = {
  id: string;
  label: string;
  blurb: string;
  questionIds: string[];
};

// ---------------------------------------------------------------------------
// Taxonomy
// ---------------------------------------------------------------------------

type TaxonomyEntry = { topicId: string; topicName: string; subtopicName: string };

const TAXONOMY: Record<string, TaxonomyEntry> = {
  loops: { topicId: "control_flow", topicName: "Control flow", subtopicName: "Loops" },
  conditionals: {
    topicId: "control_flow",
    topicName: "Control flow",
    subtopicName: "Conditionals",
  },
  arguments: { topicId: "functions", topicName: "Functions", subtopicName: "Arguments" },
  returns: { topicId: "functions", topicName: "Functions", subtopicName: "Return values" },
  lists: { topicId: "data_structures", topicName: "Data structures", subtopicName: "Lists" },
  dicts: {
    topicId: "data_structures",
    topicName: "Data structures",
    subtopicName: "Dictionaries",
  },
  big_o: { topicId: "complexity", topicName: "Complexity", subtopicName: "Big-O" },
  slicing: { topicId: "strings", topicName: "Strings", subtopicName: "Slicing" },
};

// Seed values so a fresh session has a believable, uneven starting profile:
// higher pKnown = more confident; higher weakness = picked more often.
const TOPIC_BASE_PKNOWN: Record<string, number> = {
  control_flow: 0.58,
  functions: 0.44,
  data_structures: 0.36,
  complexity: 0.29,
  strings: 0.63,
};

const SUBTOPIC_BASE_WEAKNESS: Record<string, number> = {
  loops: 0.42,
  conditionals: 0.5,
  arguments: 0.62,
  returns: 0.48,
  lists: 0.55,
  dicts: 0.68,
  big_o: 0.78,
  slicing: 0.31,
};

function taxonomyFor(subtopicId: string): TaxonomyEntry {
  const entry = TAXONOMY[subtopicId];
  if (!entry) throw new Error(`Unknown subtopic: ${subtopicId}`);
  return entry;
}

// ---------------------------------------------------------------------------
// Question bank
// ---------------------------------------------------------------------------

type QuestionSeed = Omit<Question, "topicId" | "topicName" | "subtopicName"> & {
  subtopicId: string;
};

const QUESTION_SEEDS: QuestionSeed[] = [
  {
    id: "q-range-list",
    subtopicId: "loops",
    difficulty: "easy",
    type: "multiple_choice",
    prompt: "What does list(range(3)) evaluate to?",
    options: ["[0, 1, 2]", "[1, 2, 3]", "[0, 1, 2, 3]", "[3]"],
    correctOptionIndex: 0,
    explanation: "range(3) yields 0, 1, 2 — it starts at 0 and stops before the argument.",
    feedbackCorrect: "Right — range stops before its argument, so you get 0 through 2.",
    feedbackIncorrect: "range(n) starts at 0 and stops before n, so list(range(3)) is [0, 1, 2].",
  },
  {
    id: "q-and-condition",
    subtopicId: "conditionals",
    difficulty: "medium",
    type: "multiple_choice",
    prompt: "What does this program print?",
    code: 'x = 5\nif x > 3 and x < 10:\n    print("mid")\nelse:\n    print("out")',
    options: ["mid", "out", "nothing", "an error"],
    correctOptionIndex: 0,
    explanation: "5 is greater than 3 and less than 10, so both sides of the and are true.",
    feedbackCorrect: "Correct — both comparisons hold, so the if branch runs.",
    feedbackIncorrect: 'x is 5: 5 > 3 is true and 5 < 10 is true, so the if branch prints "mid".',
  },
  {
    id: "q-for-string",
    subtopicId: "loops",
    difficulty: "easy",
    type: "true_false",
    prompt: "A for loop can iterate directly over the characters of a string.",
    correctBoolean: true,
    explanation: 'Strings are iterable; `for ch in "abc"` binds ch to "a", then "b", then "c".',
    feedbackCorrect: "Yes — strings are iterable, one character per step.",
    feedbackIncorrect: 'Strings are iterable in Python: for ch in "abc" walks the characters.',
  },
  {
    id: "q-sum-range",
    subtopicId: "loops",
    difficulty: "medium",
    type: "output_prediction",
    prompt: "What does this program print?",
    code: "total = 0\nfor i in range(1, 5):\n    total += i\nprint(total)",
    acceptableAnswers: ["10"],
    explanation: "range(1, 5) is 1, 2, 3, 4 and 1 + 2 + 3 + 4 = 10.",
    feedbackCorrect: "Correct — 1 + 2 + 3 + 4 = 10.",
    feedbackIncorrect: "range(1, 5) covers 1, 2, 3, 4. Adding them gives 10.",
  },
  {
    id: "q-implicit-none",
    subtopicId: "returns",
    difficulty: "easy",
    type: "short_text",
    prompt: "A function with no return statement returns which built-in value?",
    acceptableAnswers: ["None"],
    explanation: "Every function returns something; with no return statement that value is None.",
    feedbackCorrect: "Right — a missing return means the function returns None.",
    feedbackIncorrect:
      "Python functions always return a value; without a return statement it is None.",
  },
  {
    id: "q-missing-arg",
    subtopicId: "arguments",
    difficulty: "medium",
    type: "multiple_choice",
    prompt: 'Given def greet(name, greeting="hi"):, which call raises a TypeError?',
    options: ["greet()", 'greet("Ada")', 'greet("Ada", "hello")', 'greet(name="Ada")'],
    correctOptionIndex: 0,
    explanation: "name has no default, so it must be supplied. greet() supplies nothing.",
    feedbackCorrect: "Correct — name is required, so greet() is missing an argument.",
    feedbackIncorrect: "name has no default value, so greet() with no arguments raises TypeError.",
  },
  {
    id: "q-default-multiply",
    subtopicId: "arguments",
    difficulty: "medium",
    type: "output_prediction",
    prompt: "What does this program print?",
    code: "def f(a, b=2):\n    return a * b\n\nprint(f(3))",
    acceptableAnswers: ["6"],
    explanation: "b falls back to its default of 2, so the call returns 3 * 2.",
    feedbackCorrect: "Correct — b defaults to 2, so 3 * 2 is 6.",
    feedbackIncorrect: "b is not passed, so it uses its default of 2: 3 * 2 = 6.",
  },
  {
    id: "q-list-append",
    subtopicId: "lists",
    difficulty: "easy",
    type: "multiple_choice",
    prompt: "Which expression adds 4 to the end of nums = [1, 2, 3]?",
    options: ["nums.append(4)", "nums + 4", "nums.add(4)", "append(nums, 4)"],
    correctOptionIndex: 0,
    explanation: "append is the list method that adds a single item to the end, in place.",
    feedbackCorrect: "Right — append adds one item to the end of the list.",
    feedbackIncorrect: "Lists grow with the append method: nums.append(4).",
  },
  {
    id: "q-list-insert",
    subtopicId: "lists",
    difficulty: "medium",
    type: "output_prediction",
    prompt: "What does this program print?",
    code: "nums = [1, 2, 3]\nnums.insert(1, 9)\nprint(nums)",
    acceptableAnswers: ["[1, 9, 2, 3]"],
    explanation: "insert(1, 9) puts 9 at index 1 and shifts the rest of the list right.",
    feedbackCorrect: "Correct — 9 lands at index 1 and everything after it shifts right.",
    feedbackIncorrect: "insert(1, 9) places 9 at index 1: the list becomes [1, 9, 2, 3].",
  },
  {
    id: "q-dict-keys",
    subtopicId: "dicts",
    difficulty: "medium",
    type: "short_text",
    prompt: "Which dict method returns a view of the dictionary's keys?",
    acceptableAnswers: ["keys()", "keys", ".keys()"],
    explanation: "d.keys() returns a live view object over the current keys.",
    feedbackCorrect: "Right — keys() gives you a view over the dictionary's keys.",
    feedbackIncorrect: "The method is keys(): d.keys() returns a view of the keys.",
  },
  {
    id: "q-dict-len",
    subtopicId: "dicts",
    difficulty: "medium",
    type: "output_prediction",
    prompt: "What does this program print?",
    code: 'd = {"a": 1}\nd["b"] = 2\nprint(len(d))',
    acceptableAnswers: ["2"],
    explanation: "The assignment adds a second key, so the dictionary now has length 2.",
    feedbackCorrect: 'Correct — adding key "b" brings the dictionary to two entries.',
    feedbackIncorrect: 'd["b"] = 2 adds a new key, so len(d) is 2.',
  },
  {
    id: "q-dict-lookup-bigo",
    subtopicId: "big_o",
    difficulty: "medium",
    type: "multiple_choice",
    prompt: "What is the average-case time to look up a key in a Python dict?",
    options: ["O(1)", "O(log n)", "O(n)", "O(n log n)"],
    correctOptionIndex: 0,
    explanation: "Dicts are hash tables: the average key lookup does not depend on size.",
    feedbackCorrect: "Right — hash-table lookup is constant time on average.",
    feedbackIncorrect: "A dict is a hash table, so average key lookup is O(1).",
  },
  {
    id: "q-list-search-bigo",
    subtopicId: "big_o",
    difficulty: "hard",
    type: "multiple_choice",
    prompt: "Worst case, how long does it take to find a value in an unsorted list of n items?",
    options: ["O(n)", "O(1)", "O(log n)", "O(n^2)"],
    correctOptionIndex: 0,
    explanation: "With no ordering to exploit you may have to check every one of the n items.",
    feedbackCorrect: "Right — an unsorted scan may touch all n items.",
    feedbackIncorrect: "Nothing is sorted, so the search may have to check every item: O(n).",
  },
  {
    id: "q-slice-basic",
    subtopicId: "slicing",
    difficulty: "easy",
    type: "output_prediction",
    prompt: "What does this program print?",
    code: 's = "python"\nprint(s[1:4])',
    acceptableAnswers: ["yth"],
    explanation: 's[1:4] takes indexes 1, 2, 3 — "y", "t", "h" — stopping before index 4.',
    feedbackCorrect: 'Correct — indexes 1 through 3 give "yth".',
    feedbackIncorrect: 's[1:4] is characters at index 1, 2, 3: "yth".',
  },
  {
    id: "q-slice-reverse",
    subtopicId: "slicing",
    difficulty: "medium",
    type: "true_false",
    prompt: '"abc"[::-1] evaluates to "cba".',
    correctBoolean: true,
    explanation: "A step of -1 walks the sequence backwards, reversing it.",
    feedbackCorrect: "Yes — a step of -1 reverses the string.",
    feedbackIncorrect: 'The [::-1] slice steps backwards through the string, so you get "cba".',
  },
  {
    id: "q-parsons-sum",
    subtopicId: "loops",
    difficulty: "medium",
    type: "parsons",
    prompt: "Put these lines in order so the function returns the sum of a list of numbers.",
    steps: [
      { id: "def", text: "def total(values):" },
      { id: "init", text: "    result = 0" },
      { id: "for", text: "    for v in values:" },
      { id: "add", text: "        result += v" },
      { id: "return", text: "    return result" },
    ],
    explanation:
      "Define the function, start an accumulator at 0, loop over the values adding each one, then return the accumulator.",
    feedbackCorrect: "Correct — accumulate into result, then return it after the loop.",
    feedbackPartial:
      "Some lines are in place. The accumulator has to start before the loop and be returned after it.",
    feedbackIncorrect:
      "The order is: def, then result = 0, then the for loop, then result += v, then return result.",
  },
];

export const QUESTIONS: Question[] = QUESTION_SEEDS.map((seed) => {
  const tax = taxonomyFor(seed.subtopicId);
  return {
    ...seed,
    topicId: tax.topicId,
    topicName: tax.topicName,
    subtopicName: tax.subtopicName,
  };
});

const QUESTION_BY_ID = new Map(QUESTIONS.map((question) => [question.id, question]));

export function questionById(id: string): Question | undefined {
  return QUESTION_BY_ID.get(id);
}

export const PRACTICE_SETS: PracticeSet[] = [
  {
    id: "foundations",
    label: "Python foundations",
    blurb: "Loops, conditionals and functions — the basics, adaptively paced.",
    questionIds: [
      "q-range-list",
      "q-and-condition",
      "q-for-string",
      "q-sum-range",
      "q-implicit-none",
      "q-missing-arg",
      "q-default-multiply",
      "q-parsons-sum",
      "q-slice-basic",
      "q-slice-reverse",
    ],
  },
  {
    id: "structures",
    label: "Data structures & complexity",
    blurb: "Lists, dictionaries and the Big-O that comes with them.",
    questionIds: [
      "q-list-append",
      "q-list-insert",
      "q-dict-keys",
      "q-dict-len",
      "q-dict-lookup-bigo",
      "q-list-search-bigo",
    ],
  },
  {
    id: "mixed",
    label: "Full mixed review",
    blurb: "Every topic in one set — the widest spread of question types.",
    questionIds: QUESTIONS.map((question) => question.id),
  },
];

export function practiceSetById(id: string): PracticeSet | undefined {
  return PRACTICE_SETS.find((set) => set.id === id);
}

// ---------------------------------------------------------------------------
// Progress model
// ---------------------------------------------------------------------------

export type TopicMastery = {
  topicId: string;
  topicName: string;
  pKnown: number;
  band: "low" | "medium" | "high";
};

export type SubtopicWeakness = {
  subtopicId: string;
  subtopicName: string;
  topicName: string;
  weakness: number;
};

export type Progress = {
  topics: TopicMastery[];
  subtopics: SubtopicWeakness[];
};

function band(pKnown: number): TopicMastery["band"] {
  if (pKnown < 0.4) return "low";
  if (pKnown < 0.7) return "medium";
  return "high";
}

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));

export function initialProgress(set: PracticeSet): Progress {
  const questions = set.questionIds
    .map((id) => QUESTION_BY_ID.get(id))
    .filter((question): question is Question => question !== undefined);

  const topicIds = [...new Set(questions.map((question) => question.topicId))];
  const subtopicIds = [...new Set(questions.map((question) => question.subtopicId))];

  return {
    topics: topicIds.map((topicId) => {
      const named = questions.find((question) => question.topicId === topicId);
      const pKnown = TOPIC_BASE_PKNOWN[topicId] ?? 0.5;
      return {
        topicId,
        topicName: named?.topicName ?? topicId,
        pKnown,
        band: band(pKnown),
      };
    }),
    subtopics: subtopicIds.map((subtopicId) => {
      const tax = taxonomyFor(subtopicId);
      return {
        subtopicId,
        subtopicName: tax.subtopicName,
        topicName: tax.topicName,
        weakness: SUBTOPIC_BASE_WEAKNESS[subtopicId] ?? 0.5,
      };
    }),
  };
}

// ---------------------------------------------------------------------------
// Seeded PRNG — stands in for the real weakness-weighted roulette.
// ---------------------------------------------------------------------------

function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function hashString(input: string): number {
  let h = 2166136261;
  for (let i = 0; i < input.length; i += 1) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

// ---------------------------------------------------------------------------
// Adaptive selection
// ---------------------------------------------------------------------------

export type SelectionResult = {
  question: Question;
  ordinal: number;
  requestedDifficulty: Difficulty;
  servedDifficulty: Difficulty;
  /** True when the set had nothing at the requested difficulty for this subtopic. */
  fallbackUsed: boolean;
};

export function selectNextQuestion(args: {
  set: PracticeSet;
  progress: Progress;
  answeredIds: string[];
  seed: number;
}): SelectionResult | null {
  const { set, progress, answeredIds, seed } = args;
  const pool = set.questionIds
    .map((id) => QUESTION_BY_ID.get(id))
    .filter(
      (question): question is Question =>
        question !== undefined && !answeredIds.includes(question.id),
    );
  if (pool.length === 0) return null;

  const random = mulberry32(seed + answeredIds.length * 101);
  const weightFor = (question: Question) => {
    const weakness =
      progress.subtopics.find((entry) => entry.subtopicId === question.subtopicId)?.weakness ?? 0.5;
    // Floor so no question in the pool is ever impossible to draw.
    return 0.15 + weakness;
  };

  const totalWeight = pool.reduce((sum, question) => sum + weightFor(question), 0);
  let ticket = random() * totalWeight;
  let picked = pool[0];
  for (const question of pool) {
    ticket -= weightFor(question);
    if (ticket <= 0) {
      picked = question;
      break;
    }
  }

  const topicPKnown =
    progress.topics.find((entry) => entry.topicId === picked.topicId)?.pKnown ?? 0.5;
  const requestedDifficulty: Difficulty =
    topicPKnown < 0.4 ? "easy" : topicPKnown < 0.7 ? "medium" : "hard";

  // Prefer a question in the same subtopic at the difficulty the mastery calls
  // for; fall back to the roulette pick if the set has nothing that matches.
  const sameSubtopic = pool.filter((question) => question.subtopicId === picked.subtopicId);
  const atRequested = sameSubtopic.find((question) => question.difficulty === requestedDifficulty);
  const served = atRequested ?? picked;

  return {
    question: served,
    ordinal: answeredIds.length + 1,
    requestedDifficulty,
    servedDifficulty: served.difficulty,
    fallbackUsed: served.difficulty !== requestedDifficulty,
  };
}

// ---------------------------------------------------------------------------
// Scoring
// ---------------------------------------------------------------------------

export type ScoreLabel = "correct" | "partial" | "incorrect";

export type ScoreResult = {
  score: number;
  label: ScoreLabel;
  detail: string;
  /** Present for parsons — how many lines landed in the right place. */
  passedChecks?: number;
  totalChecks?: number;
};

function normalize(value: string): string {
  return value.trim().replace(/\s+/g, " ");
}

function looseEqual(a: string, b: string): boolean {
  const na = normalize(a).toLowerCase();
  const nb = normalize(b).toLowerCase();
  if (na === nb) return true;
  return na.replace(/\s+/g, "") === nb.replace(/\s+/g, "");
}

function tokenOverlap(a: string, b: string): number {
  const setA = new Set(normalize(a).toLowerCase().split(" ").filter(Boolean));
  const setB = new Set(normalize(b).toLowerCase().split(" ").filter(Boolean));
  if (setA.size === 0 || setB.size === 0) return 0;
  let shared = 0;
  for (const token of setA) if (setB.has(token)) shared += 1;
  return shared / new Set([...setA, ...setB]).size;
}

function labelFor(score: number): ScoreLabel {
  if (score >= 100) return "correct";
  if (score > 0) return "partial";
  return "incorrect";
}

/** Parsons answers travel as a JSON array of step ids. */
export function parseParsonsAnswer(raw: string): string[] {
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((id) => typeof id === "string") : [];
  } catch {
    return [];
  }
}

export function scoreAnswer(question: Question, rawAnswer: string): ScoreResult {
  const answer = rawAnswer ?? "";

  if (question.type === "multiple_choice") {
    const correct = String(question.correctOptionIndex) === answer.trim();
    const score = correct ? 100 : 0;
    return {
      score,
      label: labelFor(score),
      detail: correct ? question.feedbackCorrect : question.feedbackIncorrect,
    };
  }

  if (question.type === "true_false") {
    const chosen = answer.trim().toLowerCase();
    const correct =
      (chosen === "true" && question.correctBoolean === true) ||
      (chosen === "false" && question.correctBoolean === false);
    const score = correct ? 100 : 0;
    return {
      score,
      label: labelFor(score),
      detail: correct ? question.feedbackCorrect : question.feedbackIncorrect,
    };
  }

  if (question.type === "short_text" || question.type === "output_prediction") {
    const candidates = question.acceptableAnswers ?? [];
    if (candidates.some((candidate) => looseEqual(candidate, answer))) {
      return { score: 100, label: "correct", detail: question.feedbackCorrect };
    }
    const bestOverlap = candidates.reduce(
      (best, candidate) => Math.max(best, tokenOverlap(candidate, answer)),
      0,
    );
    if (answer.trim() !== "" && bestOverlap >= 0.5) {
      const score = clamp(Math.round(bestOverlap * 90), 40, 85);
      return {
        score,
        label: "partial",
        detail:
          question.feedbackPartial ??
          "You're close — compare your answer with the expected one below.",
      };
    }
    return { score: 0, label: "incorrect", detail: question.feedbackIncorrect };
  }

  // parsons
  const correctOrder = (question.steps ?? []).map((step) => step.id);
  const submitted = parseParsonsAnswer(answer);
  const total = correctOrder.length;
  const inPlace = correctOrder.reduce(
    (count, id, index) => (submitted[index] === id ? count + 1 : count),
    0,
  );
  const score = total === 0 ? 0 : Math.round((inPlace / total) * 100);
  return {
    score,
    label: labelFor(score),
    detail:
      score >= 100
        ? question.feedbackCorrect
        : score > 0
          ? (question.feedbackPartial ?? question.feedbackIncorrect)
          : question.feedbackIncorrect,
    passedChecks: inPlace,
    totalChecks: total,
  };
}

// ---------------------------------------------------------------------------
// Mastery / weakness update
// ---------------------------------------------------------------------------

export type OutcomeShift = {
  next: Progress;
  topicId: string;
  topicName: string;
  topicBefore: number;
  topicAfter: number;
};

export function applyOutcome(progress: Progress, question: Question, score: number): OutcomeShift {
  const ratio = score / 100;
  let topicBefore = 0.5;
  let topicAfter = 0.5;
  let topicName = question.topicName;

  const topics = progress.topics.map((topic) => {
    if (topic.topicId !== question.topicId) return topic;
    const nextPKnown = clamp(topic.pKnown + (ratio - 0.5) * 0.16, 0.03, 0.98);
    topicBefore = topic.pKnown;
    topicAfter = nextPKnown;
    topicName = topic.topicName;
    return { ...topic, pKnown: nextPKnown, band: band(nextPKnown) };
  });

  const subtopics = progress.subtopics.map((subtopic) => {
    if (subtopic.subtopicId !== question.subtopicId) return subtopic;
    // A strong answer lowers weakness; a weak one nudges it back up.
    const nextWeakness = clamp(subtopic.weakness - (ratio - 0.35) * 0.14, 0.02, 0.99);
    return { ...subtopic, weakness: nextWeakness };
  });

  return {
    next: { topics, subtopics },
    topicId: question.topicId,
    topicName,
    topicBefore,
    topicAfter,
  };
}

// ---------------------------------------------------------------------------
// Presentation helpers shared by the screen components
// ---------------------------------------------------------------------------

export function questionTypeLabel(type: QuestionType): string {
  switch (type) {
    case "multiple_choice":
      return "Multiple choice";
    case "true_false":
      return "True or false";
    case "short_text":
      return "Short answer";
    case "output_prediction":
      return "Predict the output";
    case "parsons":
      return "Order the steps";
  }
}

export function scoreLabelText(label: ScoreLabel): string {
  switch (label) {
    case "correct":
      return "Correct";
    case "partial":
      return "Partly correct";
    case "incorrect":
      return "Not quite";
  }
}

export function masteryPercent(pKnown: number): number {
  return clamp(Math.round(pKnown * 100), 0, 100);
}

export function weaknessPercent(weakness: number): number {
  return clamp(Math.round(weakness * 100), 0, 100);
}

/** Deterministic shuffle so a parsons puzzle looks the same across reloads. */
export function shuffledStepIds(question: Question): string[] {
  const ids = (question.steps ?? []).map((step) => step.id);
  const random = mulberry32(hashString(question.id));
  for (let i = ids.length - 1; i > 0; i -= 1) {
    const j = Math.floor(random() * (i + 1));
    [ids[i], ids[j]] = [ids[j], ids[i]];
  }
  // Guard against the shuffle landing on the correct order.
  const correct = (question.steps ?? []).map((step) => step.id);
  if (ids.join() === correct.join() && ids.length > 1) {
    [ids[0], ids[1]] = [ids[1], ids[0]];
  }
  return ids;
}
