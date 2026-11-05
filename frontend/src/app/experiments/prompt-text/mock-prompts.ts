/**
 * Mock prompts for `/experiments/prompt-text`. The two `stored` Python rows are copied verbatim
 * from the dev database (they already contain Markdown). Every other prompt is hand-written to
 * show what the proposed generator rules would produce for that subject. TODO(real): none of
 * these are fetched; this page never calls the API.
 */

export type MockPrompt = {
  id: string;
  subject: string;
  type: string;
  source: "stored" | "written";
  prompt: string;
  options?: string[];
};

export const SUBJECTS = [
  "Intro Python",
  "Calculus",
  "Statistics",
  "Biology",
  "Chemistry",
  "US History",
  "Literature",
] as const;

export const MOCK_PROMPTS: MockPrompt[] = [
  {
    id: "py-debug-stored",
    subject: "Intro Python",
    type: "Debugging",
    source: "stored",
    prompt:
      "The following function is intended to create a histogram, counting how many times each letter appears in the given string `s`. However, the function is not working correctly. Identify the issue and provide a corrected version of the function.\n\n```python\ndef histogram(s):\n    d = dict()\n    for c in s:\n        d.get(c, 0) += 1\n    return d\n```",
  },
  {
    id: "py-mc-stored",
    subject: "Intro Python",
    type: "Multiple choice",
    source: "stored",
    prompt:
      "Given the following Python code snippet:\n```python\nx = 5\ny = 3\nresult = (x > y) or (x < 10) and not (x == 0)\n```\nWhat is the value of `result` and why?",
    options: [
      "`True`, because `and` binds tighter than `or`",
      "`False`, because `not (x == 0)` is evaluated first",
      "`True`, because expressions are evaluated left to right only",
      "It raises a `SyntaxError`",
    ],
  },
  {
    id: "py-coding",
    subject: "Intro Python",
    type: "Coding",
    source: "written",
    prompt:
      "Write `count_vowels(s)` that returns how many vowels are in `s`.\n\n- Count `a`, `e`, `i`, `o`, `u` in either case.\n- Return `0` for an empty string.\n- Do not use `re`.",
  },
  {
    id: "py-parsons",
    subject: "Intro Python",
    type: "Parsons",
    source: "written",
    prompt:
      "Arrange the lines so the function returns the largest value in `nums`.\n\n- Assume `nums` is not empty.\n- One line is a distractor and is not used.",
  },
  {
    id: "calc-equation",
    subject: "Calculus",
    type: "Equation response",
    source: "written",
    prompt:
      "Find $f'(x)$ for\n\n$$f(x) = x^3 \\sin x$$\n\nSimplify your answer.",
  },
  {
    id: "calc-numeric",
    subject: "Calculus",
    type: "Numeric response",
    source: "written",
    prompt:
      "Evaluate the integral. Give your answer to three decimal places.\n\n$$\\int_0^{\\pi/2} \\cos^2 x \\, dx$$",
  },
  {
    id: "stats-numeric",
    subject: "Statistics",
    type: "Numeric response",
    source: "written",
    prompt:
      "A clinic records waiting times (minutes) for five patients on Monday.\n\n| Patient | Wait |\n| --- | --- |\n| A | 12 |\n| B | 7 |\n| C | 15 |\n| D | 9 |\n| E | 22 |\n\nCompute the sample standard deviation $s$ of the waiting times. Round to one decimal place.",
  },
  {
    id: "stats-tf",
    subject: "Statistics",
    type: "True / false",
    source: "written",
    prompt:
      "A 95% confidence interval for $\\mu$ means there is a 95% probability that $\\mu$ lies inside the interval you computed.",
    options: ["True", "False"],
  },
  {
    id: "bio-mc",
    subject: "Biology",
    type: "Multiple choice",
    source: "written",
    prompt:
      "A cell is placed in a solution whose solute concentration is higher than the cytoplasm's.\n\nWhat happens to the cell's volume?",
    options: [
      "It increases as water moves in",
      "It decreases as water moves out",
      "It stays the same because the membrane blocks water",
      "It increases as solute moves in",
    ],
  },
  {
    id: "chem-numeric",
    subject: "Chemistry",
    type: "Numeric response",
    source: "written",
    prompt:
      "How many moles of $\\text{O}_2$ are needed to burn 3.0 mol of $\\text{CH}_4$ completely?\n\n$$\\text{CH}_4 + 2\\,\\text{O}_2 \\rightarrow \\text{CO}_2 + 2\\,\\text{H}_2\\text{O}$$",
  },
  {
    id: "hist-short",
    subject: "US History",
    type: "Short answer",
    source: "written",
    prompt:
      "Read the excerpt from Lincoln's Second Inaugural Address (1865).\n\n> With malice toward none, with charity for all, with firmness in the right as God gives us to see the right, let us strive on to finish the work we are in, to bind up the nation's wounds…\n\nIn two or three sentences, explain what this passage suggests about Lincoln's plans for the South after the war.",
  },
  {
    id: "lit-short",
    subject: "Literature",
    type: "Short answer",
    source: "written",
    prompt:
      "In *Of Mice and Men*, Steinbeck ends the novel where it began, at the pool by the Salinas River.\n\nExplain what this circular structure adds to the ending. Refer to one specific detail from the final chapter.",
  },
];
