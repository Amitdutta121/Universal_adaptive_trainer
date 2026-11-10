/**
 * A simulated class that does learn, to show what the learning charts look like when they work.
 * The only fake data in this folder besides the CS189 snapshot.
 *
 * TODO(real): stand-in for a real class's answers. Each simulated student meets the six CS189
 * subtopics in order and moves on the way the adaptive tutor does: once the tutor's BKT mastery
 * estimate reaches TOPIC_ADVANCE_CEILING (0.60), updated after each answer with the engine's
 * default parameters (app/domain/mastery.py, app/adaptive/state.py). Nine answers is a cap for
 * the mock only, so a student who never learns still ends; the real engine has none. Whether the
 * simulated student actually knows a subtopic is a separate BKT draw: a starting chance of
 * knowing it, a chance of learning it after each answer, a guess and a slip. Difficulty steps up after a
 * right answer and down after a miss, and changes the chance of a right answer. A seeded
 * random generator makes every load identical.
 */

import type { Answer, Difficulty } from "./learning-analysis";

const SUBTOPICS = [
  "Using the REPL and basic tooling",
  "Literals and types",
  "Variables and expressions",
  "Conditionals",
  "Loops and iteration",
  "Loop control statements",
];

const STUDENTS = 36;
const LEARN = 0.22;
const GUESS = 0.25;
const SLIP = 0.1;
const DIFFICULTY_SHIFT: Record<Difficulty, number> = { easy: 0.1, medium: 0, hard: -0.15 };
const LADDER: Difficulty[] = ["easy", "medium", "hard"];

/** The engine's advance threshold and default BKT parameters (app/domain/mastery.py). */
const TOPIC_ADVANCE_CEILING = 0.6;
const TUTOR = { init: 0.1, learn: 0.03, guess: 0.3, slip: 0.05 };
const MAX_ANSWERS = 9;

/** The tutor's mastery estimate after one right/wrong answer: BKT evidence, then learning. */
export function updateMastery(pKnown: number, correct: boolean): number {
  const known = pKnown * (correct ? 1 - TUTOR.slip : TUTOR.slip);
  const unknown = (1 - pKnown) * (correct ? TUTOR.guess : 1 - TUTOR.guess);
  const posterior = known + unknown > 0 ? known / (known + unknown) : pKnown;
  return posterior + (1 - posterior) * TUTOR.learn;
}

/** mulberry32: a small seeded generator, so the mock is the same on every load. */
function seeded(seed: number) {
  let state = seed;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Monday of the simulated course's first week. */
const COURSE_START = Date.UTC(2026, 8, 7);
const DAY_MS = 86_400_000;

function simulate(): Answer[] {
  const random = seeded(189);
  const answers: Answer[] = [];
  for (let s = 1; s <= STUDENTS; s++) {
    const student = `m${s}`;
    // Earlier subtopics are easier to walk in knowing. Subtopic i is practised in week i+1,
    // on a day of the student's choosing.
    SUBTOPICS.forEach((subtopic, position) => {
      const day = COURSE_START + (position * 7 + Math.floor(random() * 5)) * DAY_MS;
      let known = random() < 0.35 - position * 0.04;
      let level = 0;
      let mastery = TUTOR.init;
      for (let attempt = 0; attempt < MAX_ANSWERS && mastery < TOPIC_ADVANCE_CEILING; attempt++) {
        const difficulty = LADDER[level];
        const base = known ? 1 - SLIP : GUESS;
        const correct = random() < Math.min(0.98, Math.max(0.02, base + DIFFICULTY_SHIFT[difficulty]));
        const at = new Date(day + (9 + attempt) * 3_600_000).toISOString();
        answers.push({ student, subtopic, difficulty, correct, at });
        mastery = updateMastery(mastery, correct);
        level = correct ? Math.min(2, level + 1) : Math.max(0, level - 1);
        if (!known && random() < LEARN) known = true;
      }
    });
  }
  return answers;
}

export const MOCK_CLASS: Answer[] = simulate();
