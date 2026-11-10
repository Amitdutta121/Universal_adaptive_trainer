/**
 * Mock questions with figures, as a student would be served them.
 *
 * TODO(real): none of this comes from the API. `figure` is the proposed addition to
 * `ServedQuestionOut`; the key and explanation stand in for the scored result.
 *
 * The "computed" questions are real output: the SVGs in `public/experiments/figure-questions/` and
 * their keys were produced by one PrairieLearn-style `generate(seed)` Python program (matplotlib)
 * run for seeds 11, 23 and 47, so the figure and the key of each variant come from the same data.
 */

import type { ServedQuestionOut } from "@/lib/api/types";
import type { ChartPayload } from "@/components/tutorial/types";

export type QuestionFigure =
  | { kind: "mermaid"; source: string; caption?: string }
  | { kind: "chart"; chart: ChartPayload["chart"]; caption?: string }
  | { kind: "svg"; src: string; caption: string };

export type FigureKind = QuestionFigure["kind"];

export const FIGURE_KIND_LABEL: Record<FigureKind, string> = {
  mermaid: "Diagram",
  chart: "Chart",
  svg: "Computed figure",
};

/** One copy of a question: a fixed question has one, a computed one has one per seed. */
export type Variant = {
  seed?: number;
  question: ServedQuestionOut;
  /** Absent for a text-only question. */
  figure?: QuestionFigure;
  /** MCQ: the option index; true/false: "true" | "false"; numeric: the number; output: the text. */
  key: string;
  explanation: string;
};

export type MockFigureQuestion = {
  id: string;
  subject: string;
  variants: Variant[];
};

let nextAttempt = 9000;

export function served(
  type: NonNullable<ServedQuestionOut["question_type"]>,
  subtopic: string,
  prompt: string,
  extra: Partial<ServedQuestionOut> = {},
): ServedQuestionOut {
  nextAttempt += 1;
  return {
    training_session_id: 1,
    attempt_id: nextAttempt,
    ordinal: 1,
    resumed: false,
    fallback_used: false,
    live: false,
    requested_difficulty: "medium",
    served_difficulty: "medium",
    subtopic_id: null,
    subtopic_name: subtopic,
    question_id: nextAttempt,
    question_type: type,
    prompt,
    ...extra,
  };
}

const flowchart: MockFigureQuestion = {
  id: "flowchart",
  subject: "Intro Python",
  variants: [
    {
      question: served(
        "multiple_choice",
        "Conditionals",
        "The flowchart runs once, starting with `x = 7`. What does it print?",
        { options: ["11", "22", "big", "3"] },
      ),
      figure: {
        kind: "mermaid",
        source: `flowchart TD
  A([x = 7]) --> B{x % 2 == 0?}
  B -- yes --> C[x = x // 2]
  B -- no --> D[x = 3 * x + 1]
  C --> E{x > 10?}
  D --> E
  E -- yes --> F[/print big/]
  E -- no --> G[/print x/]`,
      },
      key: "2",
      explanation: "7 is odd, so x becomes 22. 22 > 10, so it prints big.",
    },
  ],
};

const stateMachine: MockFigureQuestion = {
  id: "state-machine",
  subject: "Theory of computation",
  variants: [
    {
      question: served(
        "true_false",
        "Finite automata",
        "The automaton accepts the string `abab`.",
      ),
      figure: {
        kind: "mermaid",
        // A flowchart, not stateDiagram-v2: Mermaid's state layout overlaps self-loop labels.
        source: `flowchart LR
  start(( )) --> q0((q0))
  q0 -- a --> q1((q1))
  q0 -- b --> q0
  q1 -- a --> q1
  q1 -- b --> q2(((q2)))
  q2 -- a --> q1
  q2 -- b --> q0`,
        caption: "Starts at q0. q2, drawn with a double circle, is the only accepting state.",
      },
      key: "true",
      explanation: "q0 →a q1 →b q2 →a q1 →b q2, which accepts.",
    },
  ],
};

const classDiagram: MockFigureQuestion = {
  id: "class-diagram",
  subject: "Intro Python",
  variants: [
    {
      question: served(
        "multiple_choice",
        "Inheritance",
        "`p = Puppy('Rex')`. Whose method runs when you call `p.speak()`?",
        { options: ["Animal", "Dog", "Puppy", "None: it raises AttributeError"] },
      ),
      figure: {
        kind: "mermaid",
        source: `classDiagram
  class Animal {
    +name
    +speak()
    +move()
  }
  class Dog {
    +speak()
  }
  class Puppy {
    +play()
  }
  Animal <|-- Dog
  Dog <|-- Puppy`,
      },
      key: "1",
      explanation: "Puppy has no speak(), so lookup goes to its parent Dog, which overrides it.",
    },
  ],
};

const barChart: MockFigureQuestion = {
  id: "bar-chart",
  subject: "Data science",
  variants: [
    {
      question: served(
        "numeric_response",
        "Reading charts",
        "By how many units did sales rise from March to April?",
        { answer_hint: "Give a whole number." },
      ),
      figure: {
        kind: "chart",
        chart: {
          type: "bar",
          data: {
            labels: ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
            datasets: [{ label: "Units sold", data: [120, 135, 128, 160, 172, 165] }],
          },
        },
      },
      key: "32",
      explanation: "April 160 − March 128 = 32.",
    },
  ],
};

const lossCurve: MockFigureQuestion = {
  id: "loss-curve",
  subject: "Machine learning",
  variants: [
    {
      question: served(
        "multiple_choice",
        "Overfitting",
        "After which epoch does the model start to overfit?",
        { options: ["Epoch 3", "Epoch 6", "Epoch 8", "Epoch 10"] },
      ),
      figure: {
        kind: "chart",
        chart: {
          type: "line",
          data: {
            labels: ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"],
            datasets: [
              {
                label: "Training loss",
                data: [1.1, 0.82, 0.64, 0.52, 0.43, 0.37, 0.32, 0.28, 0.25, 0.22],
              },
              {
                label: "Validation loss",
                data: [1.2, 0.95, 0.8, 0.7, 0.64, 0.61, 0.63, 0.68, 0.74, 0.81],
              },
            ],
          },
        },
      },
      key: "1",
      explanation:
        "Validation loss is lowest at epoch 6 and rises after it, while training loss keeps falling.",
    },
  ],
};

// Copied from the generator's output (see the header comment).
const BOXPLOT = [
  { seed: 11, correct: 2, explanation: "IQRs: Section A 10.0, Section B 6.5, Section C 19.4." },
  { seed: 23, correct: 0, explanation: "IQRs: Section A 18.3, Section B 13.8, Section C 6.2." },
  { seed: 47, correct: 2, explanation: "IQRs: Section A 7.8, Section B 10.1, Section C 15.6." },
];

const HISTOGRAM = [
  { seed: 11, answer: 4, explanation: "The 80–90 and 90–100 bars hold 4 and 0 students." },
  { seed: 23, answer: 14, explanation: "The 80–90 and 90–100 bars hold 9 and 5 students." },
  { seed: 47, answer: 19, explanation: "The 80–90 and 90–100 bars hold 15 and 4 students." },
];

const boxplot: MockFigureQuestion = {
  id: "boxplot",
  subject: "Data science",
  variants: BOXPLOT.map((v) => ({
    seed: v.seed,
    question: served(
      "multiple_choice",
      "Spread and quartiles",
      "Which section's exam scores have the largest interquartile range?",
      { options: ["Section A", "Section B", "Section C"] },
    ),
    figure: {
      kind: "svg",
      src: `/experiments/figure-questions/boxplot-${v.seed}.svg`,
      caption: "Box plots of exam scores for three sections.",
    },
    key: String(v.correct),
    explanation: v.explanation,
  })),
};

const histogram: MockFigureQuestion = {
  id: "histogram",
  subject: "Data science",
  variants: HISTOGRAM.map((v) => ({
    seed: v.seed,
    question: served(
      "numeric_response",
      "Histograms",
      "How many students scored 80 or above?",
      { answer_hint: "Give a whole number." },
    ),
    figure: {
      kind: "svg",
      src: `/experiments/figure-questions/histogram-${v.seed}.svg`,
      caption: "Quiz scores, in bins of 10 points.",
    },
    key: String(v.answer),
    explanation: v.explanation,
  })),
};

export const OTHER_SUBJECT_QUESTIONS: MockFigureQuestion[] = [
  flowchart,
  stateMachine,
  classDiagram,
  barChart,
  lossCurve,
  boxplot,
  histogram,
];
