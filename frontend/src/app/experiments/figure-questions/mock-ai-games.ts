/**
 * Mock questions for CS 681 AI in Games, with and without figures.
 *
 * TODO(real): course 9 has no curriculum or questions in the dev database yet, so the subtopics
 * are a typical game-AI syllabus. Keys were checked by running the arithmetic in Python (minimax,
 * alpha-beta pruning, UCB1, the Q-learning update). The grid SVGs and their keys are real output
 * of the `generate(seed)` program (breadth-first search on a random 8x8 grid) for seeds 11, 23, 47.
 */

import { type MockFigureQuestion, served } from "./mock-figure-questions";

const SUBJECT = "CS 681 AI in Games";

const GAME_TREE = `flowchart TD
  A["A · MAX"] --> B["B · MIN"]
  A --> C["C · MIN"]
  A --> D["D · MIN"]
  B --> b1((3))
  B --> b2((12))
  B --> b3((8))
  C --> c1((2))
  C --> c2((4))
  C --> c3((6))
  D --> d1((14))
  D --> d2((5))
  D --> d3((2))`;

const minimax: MockFigureQuestion = {
  id: "minimax",
  subject: SUBJECT,
  variants: [
    {
      question: served("numeric_response", "Minimax", "What value does minimax back up to the root A?", {
        answer_hint: "Give a whole number.",
      }),
      figure: { kind: "mermaid", source: GAME_TREE, caption: "Leaves are utilities for MAX." },
      key: "3",
      explanation: "B = min(3, 12, 8) = 3, C = 2, D = 2, so A = max(3, 2, 2) = 3.",
    },
  ],
};

const alphaBeta: MockFigureQuestion = {
  id: "alpha-beta",
  subject: SUBJECT,
  variants: [
    {
      question: served(
        "multiple_choice",
        "Alpha-beta pruning",
        "Alpha-beta search visits the children left to right. Which leaves are never evaluated?",
        { options: ["4 and 6 under C", "12 and 8 under B", "5 and 2 under D", "None"] },
      ),
      figure: { kind: "mermaid", source: GAME_TREE, caption: "Leaves are utilities for MAX." },
      key: "0",
      explanation:
        "After B, alpha = 3. C's first leaf is 2 ≤ 3, so C cannot beat B and 4, 6 are pruned. D's leaves 14 and 5 stay above 3, so all of D is searched.",
    },
  ],
};

const behaviourTree: MockFigureQuestion = {
  id: "behaviour-tree",
  subject: SUBJECT,
  variants: [
    {
      question: served(
        "multiple_choice",
        "Behaviour trees",
        "The guard heard a noise but cannot see the player. Which action runs this tick?",
        { options: ["Attack", "Investigate", "Patrol", "Nothing: the tree fails"] },
      ),
      figure: {
        kind: "mermaid",
        source: `flowchart TD
  R{{"? Selector"}} --> S1["→ Sequence"]
  R --> S2["→ Sequence"]
  R --> P[Patrol]
  S1 --> c1(["Can see player?"])
  S1 --> a1[Attack]
  S2 --> c2(["Heard noise?"])
  S2 --> a2[Investigate]`,
        caption: "Children run left to right. Rounded nodes are conditions.",
      },
      key: "1",
      explanation:
        "The first sequence fails on its condition, so the selector tries the second: the noise check succeeds and Investigate runs. Patrol is never reached.",
    },
  ],
};

const fsm: MockFigureQuestion = {
  id: "fsm",
  subject: SUBJECT,
  variants: [
    {
      question: served(
        "true_false",
        "Finite state machines",
        "An enemy in Patrol with low health that sees the player goes straight to Flee.",
      ),
      figure: {
        kind: "mermaid",
        source: `flowchart LR
  Patrol -- sees player --> Chase
  Chase -- in range --> Attack
  Chase -- lost player --> Patrol
  Attack -- out of range --> Chase
  Attack -- low health --> Flee
  Chase -- low health --> Flee
  Flee -- healed --> Patrol`,
      },
      key: "false",
      explanation: "Patrol has no edge to Flee. Seeing the player moves it to Chase; low health then moves it to Flee.",
    },
  ],
};

const mctsVisits: MockFigureQuestion = {
  id: "mcts-visits",
  subject: SUBJECT,
  variants: [
    {
      question: served(
        "multiple_choice",
        "Monte Carlo tree search",
        [
          "After 1,000 simulations from the root, MCTS plays the **most-visited** move (robust child).",
          "",
          "| Move | a | b | c | d |",
          "|---|---|---|---|---|",
          "| Win rate | 0.71 | 0.58 | 0.60 | 0.33 |",
          "",
          "Which move does it play?",
        ].join("\n"),
        { options: ["Move a", "Move b", "Move c", "Move d"] },
      ),
      figure: {
        kind: "chart",
        chart: {
          type: "bar",
          data: {
            labels: ["a", "b", "c", "d"],
            datasets: [{ label: "Visits", data: [120, 410, 380, 90] }],
          },
        },
        caption: "Visits per root move.",
      },
      key: "1",
      explanation:
        "Move b has the most visits (410). Move a's higher win rate comes from only 120 visits, so it is less reliable.",
    },
  ],
};

const GRID = [
  { seed: 11, answer: 22, extra: 8 },
  { seed: 23, answer: 16, extra: 2 },
  { seed: 47, answer: 16, extra: 2 },
];

const gridPath: MockFigureQuestion = {
  id: "grid-path",
  subject: SUBJECT,
  variants: GRID.map((v) => ({
    seed: v.seed,
    question: served(
      "numeric_response",
      "A* pathfinding",
      "The agent moves up, down, left or right one cell at a time and cannot enter dark cells. How many moves does the shortest path from S to G take?",
      { answer_hint: "Give a whole number." },
    ),
    figure: {
      kind: "svg",
      src: `/experiments/figure-questions/grid-${v.seed}.svg`,
      caption: "An 8 × 8 grid. Dark cells are walls.",
    },
    key: String(v.answer),
    explanation: `The shortest path takes ${v.answer} moves: the walls force ${v.extra} more than the Manhattan distance of 14.`,
  })),
};

// Text only: no figure.

const ucb1: MockFigureQuestion = {
  id: "ucb1",
  subject: SUBJECT,
  variants: [
    {
      question: served(
        "numeric_response",
        "Monte Carlo tree search",
        "A child node has won 6 of its 10 visits, and its parent has 50 visits. With $c = \\sqrt{2}$, what is its UCB1 score $\\frac{w}{n} + c\\sqrt{\\frac{\\ln N}{n}}$?",
        { answer_hint: "Round to 2 decimal places." },
      ),
      key: "1.48",
      explanation: "0.6 + 1.414 × √(ln 50 / 10) = 0.6 + 1.414 × 0.626 ≈ 1.48.",
    },
  ],
};

const admissible: MockFigureQuestion = {
  id: "admissible",
  subject: SUBJECT,
  variants: [
    {
      question: served(
        "multiple_choice",
        "A* pathfinding",
        "On a 4-connected grid where every move costs 1, which heuristic is admissible for A*?",
        {
          options: [
            "Manhattan distance",
            "2 × Manhattan distance",
            "Squared Euclidean distance",
            "Manhattan distance + number of walls in the bounding box",
          ],
        },
      ),
      key: "0",
      explanation:
        "Manhattan distance never overestimates when moves are unit-cost and 4-connected. The others can exceed the true cost.",
    },
  ],
};

const alphaBetaTf: MockFigureQuestion = {
  id: "alpha-beta-value",
  subject: SUBJECT,
  variants: [
    {
      question: served(
        "true_false",
        "Alpha-beta pruning",
        "Alpha-beta pruning can change the value that minimax returns at the root.",
      ),
      key: "false",
      explanation:
        "It only skips branches that cannot affect the result; the root value is the same as plain minimax.",
    },
  ],
};

const qLearning: MockFigureQuestion = {
  id: "q-learning",
  subject: SUBJECT,
  variants: [
    {
      question: served(
        "output_prediction",
        "Q-learning",
        "What does this Q-learning update print?",
        {
          code: `q = 0.5          # Q(s, a)
alpha, gamma = 0.1, 0.9
reward = 1
best_next = 0.8  # max over a' of Q(s', a')

q = q + alpha * (reward + gamma * best_next - q)
print(round(q, 3))`,
        },
      ),
      key: "0.622",
      explanation: "0.5 + 0.1 × (1 + 0.9 × 0.8 − 0.5) = 0.5 + 0.1 × 1.22 = 0.622.",
    },
  ],
};

export const AI_GAMES_QUESTIONS: MockFigureQuestion[] = [
  minimax,
  alphaBeta,
  behaviourTree,
  fsm,
  mctsVisits,
  gridPath,
  ucb1,
  admissible,
  alphaBetaTf,
  qLearning,
];
