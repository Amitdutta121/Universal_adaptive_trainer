/**
 * Physics (mechanics). TODO(real): mining output, templates and examples come from the mining
 * and suggestion calls; the taxonomy and "have" counts are invented for the prototype.
 */

import type { Domain } from "./mock-types";

const h = (easy: number, medium: number, hard = 0) => ({ easy, medium, hard });

export const PHYSICS: Domain = {
  id: "physics",
  subjectLabel: "Physics",
  course: "PHYS 1A · Mechanics",
  book: {
    title: "University Physics, Volume 1 (OpenStax)",
    author: "Ling, Sanny, Moebs et al.",
    pages: 1062,
    chapters: 17,
    sections: 412,
  },
  taxonomy: { label: "Mechanics: kinematics to momentum", topics: 7, subtopics: 25 },
  questionTypes: {
    multiple_choice: "Multiple choice",
    true_false: "True / false",
    numeric_response: "Numeric response",
    equation_response: "Equation response",
  },
  mining: {
    tocTokens: 6_840,
    sectionsRouted: 45,
    sections: [
      { title: "Conceptual Questions", count: 9, kind: "conceptual" },
      { title: "Problems", count: 9, kind: "exercises" },
      { title: "Additional Problems", count: 9, kind: "exercises" },
      { title: "Challenge Problems", count: 9, kind: "exercises" },
      { title: "Learning Objectives", count: 8, kind: "objectives" },
      { title: "Answer Key", count: 1, kind: "answers" },
    ],
    itemsFound: 812,
    level: "First-year university, calculus-based",
    taskMix: [
      { label: "Single-step calculation", share: 0.41 },
      { label: "Multi-step problem", share: 0.28 },
      { label: "Conceptual reasoning", share: 0.24 },
      { label: "Challenge / derivation", share: 0.07 },
    ],
    difficultyMix: { easy: 268, medium: 361, hard: 183 },
    samples: [
      {
        text: "Can the speed of an object be negative? Explain.",
        source: "Ch 3 · Conceptual Questions · Q 5",
        inferredType: "Multiple choice",
        difficulty: "easy",
      },
      {
        text: "A cheetah can accelerate from rest to 25.0 m/s in 6.22 s. What is its acceleration?",
        source: "Ch 3 · Problems · Q 41",
        inferredType: "Numeric response",
        difficulty: "easy",
      },
      {
        text: "A ball is thrown horizontally from the top of a 60.0 m building and lands 100.0 m from the base. How long is it in the air?",
        source: "Ch 4 · Problems · Q 33",
        inferredType: "Numeric response",
        difficulty: "medium",
      },
      {
        text: "Why can a sprinter run around a curve on a flat track? Which force provides the centripetal acceleration?",
        source: "Ch 6 · Conceptual Questions · Q 21",
        inferredType: "Multiple choice",
        difficulty: "medium",
      },
      {
        text: "A block slides down a rough incline at constant speed. Find the coefficient of kinetic friction in terms of the angle.",
        source: "Ch 6 · Additional Problems · Q 97",
        inferredType: "Equation response",
        difficulty: "hard",
      },
      {
        text: "Two pucks collide on an air table and stick. Find the final velocity and the kinetic energy lost.",
        source: "Ch 9 · Challenge Problems · Q 140",
        inferredType: "Numeric response",
        difficulty: "hard",
      },
    ],
    notes: [
      "Only chapters 1 to 9 were read: chapters 10 to 17 are not in your taxonomy.",
      "The Answer Key gives final values for odd-numbered problems. It is used to check difficulty, not copied.",
      "Problems that need a figure were counted for level but no question style depends on them.",
    ],
  },
  wishes: [
    "More multi-step problems",
    "Units always required",
    "Conceptual before numbers",
    "Fewer true / false",
  ],
  templates: [
    {
      id: "ph-e-concept",
      name: "Pick the right idea about a familiar situation",
      summary: "An everyday motion or force situation; students choose the correct physics statement.",
      questionType: "multiple_choice",
      difficulty: "easy",
      checkedBy: "Choice: one correct option",
      evidence: "24% of the book's items are conceptual, mostly at this level.",
      examples: [
        {
          prompt: "A ball is thrown straight up. At the very top of its path:",
          options: [
            { text: "its velocity and acceleration are both zero" },
            { text: "its velocity is zero and its acceleration is 9.8 m/s² downward", correct: true },
            { text: "its velocity is zero and its acceleration is upward" },
            { text: "its velocity is upward and its acceleration is zero" },
          ],
          grounding: "§3.5 Free fall",
        },
        {
          prompt: "Which of these is a vector quantity?",
          options: [
            { text: "Displacement", correct: true },
            { text: "Speed" },
            { text: "Mass" },
            { text: "Time" },
          ],
          grounding: "§2.1 Scalars and vectors",
        },
      ],
    },
    {
      id: "ph-e-tf",
      name: "Catch a common misconception",
      summary: "One true-or-false statement built on a well-known wrong intuition.",
      questionType: "true_false",
      difficulty: "easy",
      checkedBy: "Choice: true or false",
      evidence: "The Conceptual Questions return to these intuitions often.",
      examples: [
        {
          prompt: "True or false: with no air resistance, a heavier object falls with a larger acceleration than a lighter one.",
          options: [{ text: "True" }, { text: "False", correct: true }],
          grounding: "§3.5 Free fall",
        },
        {
          prompt: "True or false: an object moving at constant velocity can have zero net force acting on it.",
          options: [{ text: "True", correct: true }, { text: "False" }],
          grounding: "§5.2 Newton's first law",
        },
      ],
    },
    {
      id: "ph-e-num",
      name: "One-step calculation with units",
      summary: "One formula, one substitution. The answer must carry a unit.",
      questionType: "numeric_response",
      difficulty: "easy",
      checkedBy: "Number within 2%, any compatible unit",
      evidence: "41% of the book's problems are single-step.",
      examples: [
        {
          prompt: "A car travels 150 m in 12.0 s at constant speed. What is its speed?",
          answer: "12.5 m/s (±2%; km/h accepted)",
          grounding: "§3.1 Position, displacement and average velocity",
        },
        {
          prompt: "A cyclist rides at 36 km/h. What is that speed in metres per second?",
          answer: "10 m/s (±2%)",
          grounding: "§1.3 Unit conversion",
        },
      ],
    },
    {
      id: "ph-m-num",
      name: "Two-step problem: find an intermediate, then the answer",
      summary: "Students need one result before they can get the asked-for quantity.",
      questionType: "numeric_response",
      difficulty: "medium",
      checkedBy: "Number within 2%, any compatible unit",
      evidence: "Like most of the book's Problems sections from chapter 3 on.",
      examples: [
        {
          prompt: "A ball is dropped from rest from a bridge 20.0 m above the water. Ignoring air resistance, how fast is it moving just before it hits the water?",
          answer: "19.8 m/s (±2%)",
          grounding: "§3.5 Free fall",
        },
        {
          prompt: "A 1200 kg car accelerates uniformly from rest to 25.0 m/s in 8.00 s. What net force acts on it?",
          answer: "3.75 × 10³ N (±2%)",
          grounding: "§5.3 Newton's second law",
        },
      ],
    },
    {
      id: "ph-m-graph",
      name: "Read a motion graph described in words",
      summary: "The graph's shape is given in the prompt; students say what the motion is.",
      questionType: "multiple_choice",
      difficulty: "medium",
      checkedBy: "Choice: one correct option",
      evidence: "Chapter 3 leans on position and velocity graphs.",
      examples: [
        {
          prompt: "A cart's position-time graph is a straight line sloping downward. What does this tell you about the cart?",
          options: [
            { text: "It moves with constant negative velocity", correct: true },
            { text: "It is slowing down" },
            { text: "It is at rest" },
            { text: "It has constant positive acceleration" },
          ],
          grounding: "§3.2 Instantaneous velocity and speed",
        },
        {
          prompt: "A velocity-time graph is a horizontal line at v = 4.0 m/s from t = 0 to t = 5.0 s. What is the displacement over that time?",
          options: [
            { text: "20 m", correct: true },
            { text: "0.8 m" },
            { text: "4.0 m" },
            { text: "It cannot be found from this graph" },
          ],
          grounding: "§3.6 Finding velocity and displacement from acceleration",
        },
      ],
    },
    {
      id: "ph-m-eq",
      name: "Write the formula for a standard setup",
      summary: "Students give a symbolic result in the given variables, not a number.",
      questionType: "equation_response",
      difficulty: "medium",
      checkedBy: "Expression checked for mathematical equivalence",
      evidence: "Several Additional Problems ask for answers in terms of symbols.",
      examples: [
        {
          prompt: "A block slides down a frictionless incline at angle θ. Write its acceleration along the incline in terms of g and θ.",
          answer: "a = g sin θ",
          grounding: "§6.1 Solving problems with Newton's laws",
        },
        {
          prompt: "A mass m on a string moves in a horizontal circle of radius r at speed v. Ignoring gravity, write the tension T.",
          answer: "T = m v² / r",
          grounding: "§6.3 Centripetal force",
        },
      ],
    },
    {
      id: "ph-h-multi",
      name: "Multi-step problem combining two ideas",
      summary: "Forces with friction, or momentum then energy. Students plan the steps themselves.",
      questionType: "numeric_response",
      difficulty: "hard",
      checkedBy: "Number within 2%, any compatible unit",
      evidence: "Like the Additional and Challenge Problems at the end of chapters 6 to 9.",
      examples: [
        {
          prompt: "A 5.0 kg block starts from rest and slides 3.0 m down a 30° incline. The coefficient of kinetic friction is 0.20. What is its speed at the bottom?",
          answer: "4.4 m/s (±2%)",
          grounding: "§6.2 Friction",
        },
        {
          prompt: "A 0.20 kg ball moving at 6.0 m/s hits a 0.30 kg ball at rest and they stick together. What fraction of the kinetic energy is lost?",
          answer: "0.60 (60%)",
          grounding: "§9.4 Types of collisions",
        },
      ],
    },
    {
      id: "ph-h-rank",
      name: "Reason without numbers: compare or rank cases",
      summary: "Several setups that look different; a conservation law decides the answer.",
      questionType: "multiple_choice",
      difficulty: "hard",
      checkedBy: "Choice: one correct option",
      evidence: "The book's hardest Conceptual Questions are of this kind.",
      examples: [
        {
          prompt: "Three identical blocks slide from rest down frictionless ramps of different shapes, all starting at the same height. How do their speeds at the bottom compare?",
          options: [
            { text: "All three are the same", correct: true },
            { text: "The steepest ramp gives the highest speed" },
            { text: "The longest ramp gives the highest speed" },
            { text: "It depends on the blocks' mass" },
          ],
          grounding: "§8.3 Conservation of energy",
        },
        {
          prompt: "Two carts collide on a frictionless track and stick together. Which quantity must be the same just before and just after?",
          options: [
            { text: "The total momentum", correct: true },
            { text: "The total kinetic energy" },
            { text: "Each cart's velocity" },
            { text: "The sum of the carts' speeds" },
          ],
          grounding: "§9.3 Conservation of linear momentum",
        },
      ],
    },
    {
      id: "ph-h-derive",
      name: "Derive a result in symbols",
      summary: "Students combine two or three relations to reach a closed form.",
      questionType: "equation_response",
      difficulty: "hard",
      checkedBy: "Expression checked for mathematical equivalence",
      evidence: "Matches the derivation-style Challenge Problems.",
      examples: [
        {
          prompt: "A projectile is launched at speed v₀ and angle θ above level ground. Write its range R in terms of v₀, θ and g.",
          answer: "R = v₀² sin(2θ) / g",
          grounding: "§4.3 Projectile motion",
        },
        {
          prompt: "A pendulum of length L is released from rest at angle θ from vertical. Write the bob's speed at the lowest point.",
          answer: "v = √(2gL(1 − cos θ))",
          grounding: "§8.3 Conservation of energy",
        },
      ],
    },
  ],
  reserve: [
    {
      id: "ph-h-tf",
      name: "Judge a plausible but wrong claim",
      summary: "A statement that sounds right to most students; deciding it needs a law, not intuition.",
      questionType: "true_false",
      difficulty: "hard",
      checkedBy: "Choice: true or false",
      evidence: "A hard style that is fast to answer.",
      examples: [
        {
          prompt: "True or false: in a perfectly inelastic collision, all of the kinetic energy is lost.",
          options: [{ text: "True" }, { text: "False", correct: true }],
          grounding: "§9.4 Types of collisions",
        },
        {
          prompt: "True or false: the normal force on a block on an incline always equals its weight.",
          options: [{ text: "True" }, { text: "False", correct: true }],
          grounding: "§6.1 Solving problems with Newton's laws",
        },
      ],
    },
    {
      id: "ph-e-eq",
      name: "Rearrange a formula for one variable",
      summary: "One definition, solved for the asked-for symbol.",
      questionType: "equation_response",
      difficulty: "easy",
      checkedBy: "Expression checked for mathematical equivalence",
      evidence: "A gentle start for symbolic answers.",
      examples: [
        {
          prompt: "Kinetic energy is K = ½mv². Write v in terms of K and m.",
          answer: "v = √(2K / m)",
          grounding: "§7.2 Kinetic energy",
        },
        {
          prompt: "Momentum is p = mv. Write m in terms of p and v.",
          answer: "m = p / v",
          grounding: "§9.1 Linear momentum",
        },
      ],
    },
  ],
  topics: [
    {
      id: "units",
      name: "Units, Measurement and Vectors",
      subtopics: [
        { id: "units-1", name: "Unit conversion", have: h(2, 1) },
        { id: "units-2", name: "Significant figures and estimation", have: h(1, 0) },
        { id: "units-3", name: "Vector components", have: h(2, 1) },
        { id: "units-4", name: "Vector addition", have: h(1, 1) },
      ],
    },
    {
      id: "kin1",
      name: "Motion Along a Straight Line",
      subtopics: [
        { id: "kin1-1", name: "Displacement and velocity", have: h(3, 2) },
        { id: "kin1-2", name: "Constant-acceleration equations", have: h(2, 2) },
        { id: "kin1-3", name: "Free fall", have: h(2, 1) },
        { id: "kin1-4", name: "Reading motion graphs", have: h(1, 0) },
      ],
    },
    {
      id: "kin2",
      name: "Motion in Two Dimensions",
      subtopics: [
        { id: "kin2-1", name: "Projectile motion", have: h(1, 1) },
        { id: "kin2-2", name: "Uniform circular motion", have: h(1, 0) },
        { id: "kin2-3", name: "Relative motion", have: h(0, 0) },
      ],
    },
    {
      id: "newton",
      name: "Newton's Laws",
      subtopics: [
        { id: "newton-1", name: "Free-body diagrams", have: h(2, 1) },
        { id: "newton-2", name: "Newton's second law", have: h(3, 2) },
        { id: "newton-3", name: "Newton's third-law pairs", have: h(2, 0) },
      ],
    },
    {
      id: "apps",
      name: "Applications of Newton's Laws",
      subtopics: [
        { id: "apps-1", name: "Friction", have: h(1, 1) },
        { id: "apps-2", name: "Inclined planes", have: h(1, 0) },
        { id: "apps-3", name: "Tension and pulleys", have: h(0, 0) },
        { id: "apps-4", name: "Centripetal force", have: h(0, 1) },
      ],
    },
    {
      id: "energy",
      name: "Work and Energy",
      subtopics: [
        { id: "energy-1", name: "Work done by a constant force", have: h(2, 1) },
        { id: "energy-2", name: "Work-energy theorem", have: h(1, 1) },
        { id: "energy-3", name: "Potential energy", have: h(1, 0) },
        { id: "energy-4", name: "Conservation of mechanical energy", have: h(1, 1) },
      ],
    },
    {
      id: "mom",
      name: "Momentum and Collisions",
      subtopics: [
        { id: "mom-1", name: "Impulse", have: h(0, 0) },
        { id: "mom-2", name: "Conservation of momentum", have: h(1, 0) },
        { id: "mom-3", name: "Elastic and inelastic collisions", have: h(0, 0) },
      ],
    },
  ],
};
