/*
 * Page-only mock data for G6 import-questions.html, G8 exam-export.html and G9 copy-course.html.
 * Load after assets/data-g.js. Only ADDS window.MOCK.gContent; reads MOCK, never changes it.
 * TODO(real): every value in this file is invented.
 */
(function () {
  const M = window.MOCK;

  // "2026-10-22" -> "Oct 22" (or "Oct 22, 2026" with year).
  const date = (iso, year) => iso
    ? new Date(`${iso}T12:00:00`).toLocaleDateString("en-US", year ? { month: "short", day: "numeric", year: "numeric" } : { month: "short", day: "numeric" })
    : "—";
  const addDays = (iso, n) => { const d = new Date(`${iso}T12:00:00`); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };

  // ---- G6 import ---------------------------------------------------------------------
  // TODO(real): the parser's report for one Canvas course export.
  const importFile = {
    name: "CS135-Fall2025-quizzes.zip", format: "canvas", size: "3.8 MB",
    detail: "Canvas export, 84 questions", course: "CS 135 · Fall 2025", quizzes: 10, students_with_stats: 112, with_stats: 71,
    found: 84, supported: 79, unsupported: 5, duplicates: 3,
    by_type: [["Multiple choice", "multiple_choice", 46], ["True / false", "true_false", 14], ["Fill in the blank → Output prediction", "output_prediction", 19]],
    // Confidence counts over the questions that will be imported (79 - 3 duplicates = 76).
    confidence: { low: 3, medium: 5, high: 68 },
  };
  const unsupported = [
    { where: "Quiz 2, Q9", kind: "Essay", prompt: "Explain in your own words the difference between = and ==." },
    { where: "Quiz 5, Q10", kind: "Essay", prompt: "Describe a situation where you would use a dictionary instead of a list." },
    { where: "Quiz 8, Q7", kind: "Essay", prompt: "Why is a with statement safer than calling f.close() yourself?" },
    { where: "Project check-in 1", kind: "File upload", prompt: "Upload your hangman.py." },
    { where: "Project check-in 2", kind: "File upload", prompt: "Upload word_count.py and a screenshot of one run." },
  ];
  // Exact duplicates of questions already in this course's bank (same prompt and answer).
  const duplicates = [
    { where: "Quiz 4, Q3", existing: 1000 },
    { where: "Quiz 3, Q8", existing: 1009 },
    { where: "Quiz 5, Q2", existing: 1004 },
  ];
  // The visible rows of the mapping table. p = share correct in Canvas item analysis (Fall 2025).
  const rows = [
    { id: "i07", where: "Quiz 3, Q7", type: "output_prediction", canvas: "Fill in the blank",
      prompt: "What is printed?\n\ndef f(n):\n    if n <= 1:\n        return 1\n    return n * f(n - 1)\nprint(f(4))", answer: "24",
      subtopic: "Return values", confidence: "low", why: "Tests recursion; v3 has no recursion subtopic.", p: 0.41 },
    { id: "i23", where: "Quiz 6, Q4", type: "multiple_choice", canvas: "Multiple choice",
      prompt: "Which of these creates an empty set?", answer: "set()",
      subtopic: "Set operations", confidence: "low", why: "Could also be Choosing a collection.", p: 0.58 },
    { id: "i31", where: "Quiz 7, Q1", type: "multiple_choice", canvas: "Multiple choice",
      prompt: "What is the value of `'3' + str(4 * 2)`?", answer: "'38'",
      subtopic: "Operator precedence", confidence: "low", why: "Split between Type conversion and Strings as values.", p: 0.71 },
    { id: "i12", where: "Quiz 2, Q5", type: "output_prediction", canvas: "Fill in the blank",
      prompt: "For x = 0, what does this print?\n\nprint(x != 0 and 10 / x > 1)", answer: "False",
      subtopic: "Logical operators", confidence: "medium", why: "Short-circuit evaluation; close to Comparison operators.", p: 0.49 },
    { id: "i18", where: "Quiz 4, Q6", type: "output_prediction", canvas: "Fill in the blank",
      prompt: "What is printed?\n\nnums = [3, 1, 2]\nprint(nums.sort())", answer: "None",
      subtopic: "List methods", confidence: "medium", why: "Also about return values of methods.", p: 0.33 },
    { id: "i15", where: "Quiz 3, Q2", type: "output_prediction", canvas: "Fill in the blank",
      prompt: "How many times is hi printed?\n\nfor i in range(2):\n    for j in range(3):\n        print('hi')", answer: "6",
      subtopic: "range() and counted loops", confidence: "medium", why: "Nested loops; no subtopic of its own.", p: 0.77 },
    { id: "i28", where: "Quiz 5, Q6", type: "multiple_choice", canvas: "Multiple choice",
      prompt: "What does `print({'a': 1, 'b': 2}.get('c', 0))` print?", answer: "0",
      subtopic: "Keys and values", confidence: "medium", why: "Could be Iterating a dict.", p: null },
    { id: "i35", where: "Quiz 8, Q2", type: "multiple_choice", canvas: "Multiple choice",
      prompt: "Which loop reads a file one line at a time without loading it all into memory?", answer: "for line in f:",
      subtopic: "Reading files", confidence: "medium", why: "Also uses a with statement.", p: 0.66 },
    { id: "i01", where: "Quiz 1, Q1", type: "multiple_choice", canvas: "Multiple choice",
      prompt: "What is the type of `7 // 2`?", answer: "int", subtopic: "Integers and floats", confidence: "high", why: "", p: 0.81 },
    { id: "i05", where: "Quiz 1, Q5", type: "multiple_choice", canvas: "Multiple choice",
      prompt: "Which of these is not a valid variable name?", answer: "2nd_place", subtopic: "Naming rules", confidence: "high", why: "", p: 0.88 },
    { id: "i20", where: "Quiz 4, Q1", type: "output_prediction", canvas: "Fill in the blank",
      prompt: "What is printed?\n\nprint('Monty Python'[6:10])", answer: "Pyth", subtopic: "Slicing", confidence: "high", why: "", p: 0.62 },
    { id: "i26", where: "Quiz 5, Q4", type: "true_false", canvas: "True / false",
      prompt: "After `d = {}` and `for w in ['a', 'b', 'a']: d[w] = d.get(w, 0) + 1`, d['a'] is 2.", answer: "True",
      subtopic: "Counting with dicts", confidence: "high", why: "", p: 0.55 },
  ];
  // Canvas item analysis -> difficulty. TODO(real): thresholds are a guess.
  const difficultyFromP = (p) => (p == null ? null : p >= 0.75 ? "easy" : p >= 0.45 ? "medium" : "hard");
  const failedChecks = [
    { where: "Quiz 3, Q6", prompt: "Which loop prints the numbers 1 to 5?", detail: "No correct answer is marked in the Canvas export." },
    { where: "Quiz 6, Q2", prompt: "Which of these values is immutable?", detail: "No correct answer is marked in the Canvas export." },
    { where: "Quiz 8, Q4", prompt: "What does f.readline() return at the end of a file?", detail: "Blank answer key (Canvas \"fill in the blank\" with no accepted answers)." },
  ];
  const csvColumns = [
    ["type", "multiple_choice, true_false, output_prediction, code_completion"],
    ["prompt", "Question text; code in a fenced block or after a blank line"],
    ["option_a … option_f", "Multiple choice only"],
    ["answer", "Letter for multiple choice, True/False, or the exact expected text"],
    ["topic, subtopic", "Optional; names from the active taxonomy. Left blank, the AI suggests one"],
    ["difficulty", "Optional; easy, medium or hard"],
    ["p_correct", "Optional; share of students who got it right before (0–1)"],
  ];

  // ---- G8 exam export ----------------------------------------------------------------
  const formats = [
    { id: "qti", label: "Canvas (QTI 1.2)", ext: ".zip", note: "Import in Canvas under Settings › Import course content › QTI .zip. Parsons and code questions become essay questions with the reference answer in the grader notes." },
    { id: "moodle", label: "Moodle XML", ext: ".xml", note: "Import in the Moodle question bank. Parsons questions use the Ordering question type if your site has it installed." },
    { id: "docx", label: "Word (.docx) with answer key", ext: ".docx", note: "Numbered questions, then the answer key on a new page. Edit before printing." },
    { id: "pdf", label: "PDF", ext: ".pdf", note: "Two files: the exam, and the answer key with the source section for each answer." },
  ];

  // ---- G9 copy to a new term -----------------------------------------------------------
  const terms = [
    { id: "spring2027", label: "Spring 2027", week1: "2027-01-25", ends: "2027-05-07" },
    { id: "fall2027", label: "Fall 2027", week1: "2027-08-30", ends: "2027-12-10" },
  ];

  M.gContent = {
    date, addDays, importFile, unsupported, duplicates, rows, difficultyFromP, failedChecks, csvColumns, formats, terms,
  };
})();
