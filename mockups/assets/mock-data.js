/*
 * Mock data for the whole mockup. One consistent story, read by every page as window.MOCK.
 * TODO(real): every value here is invented. Shapes follow the real domain enums
 * (app/domain/enums.py) so the backend can replace this file hop by hop.
 *
 * Pages must only READ from MOCK and keep their own changes in Alpine state
 * (a reload resets everything). Add fields here rather than hardcoding data in a page.
 */
(function () {
  // Deterministic pseudo-random so every reload shows the same numbers.
  let seed = 7;
  const rand = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;
  const pick = (arr) => arr[Math.floor(rand() * arr.length)];
  const round2 = (x) => Math.round(x * 100) / 100;

  const QUESTION_TYPES = {
    multiple_choice: { label: "Multiple choice", code: false },
    true_false: { label: "True / false", code: false },
    output_prediction: { label: "Output prediction", code: true },
    code_completion: { label: "Code completion", code: true },
    debugging: { label: "Debugging", code: true },
    parsons: { label: "Parsons (order the lines)", code: true },
    coding: { label: "Write a program", code: true },
  };

  const SUBJECTS = [
    { id: "python", label: "Programming (Python)", types: Object.keys(QUESTION_TYPES) },
    { id: "statistics", label: "Statistics", types: ["multiple_choice", "true_false"] },
    { id: "biology", label: "Biology", types: ["multiple_choice", "true_false"] },
    { id: "general", label: "Other subject", types: ["multiple_choice", "true_false"] },
  ];

  const REJECTION_REASONS = [
    ["technically_incorrect", "Technically incorrect"], ["incorrect_answer", "Incorrect answer"],
    ["incorrect_tests", "Incorrect tests"], ["not_grounded_in_source", "Not grounded in the book"],
    ["wrong_topic_subtopic", "Wrong topic / subtopic"], ["too_easy", "Too easy"],
    ["too_difficult", "Too difficult"], ["ambiguous", "Ambiguous"], ["poor_wording", "Poor wording"],
    ["poor_distractors", "Poor distractors"], ["poor_tests", "Poor tests"],
    ["not_pedagogically_useful", "Not useful for learning"],
    ["too_similar_repetitive", "Too similar to another question"], ["other", "Other"],
  ];

  const JUDGES = [
    { id: "issues", label: "Issues", summary: "Finds factual, answer and wording problems." },
    { id: "subtopic", label: "Subtopic fit", summary: "Checks the question tests the subtopic it claims." },
    { id: "difficulty", label: "Difficulty", summary: "Checks the stated difficulty matches the question." },
    { id: "generatability", label: "Generatability", summary: "Checks the section can support this question at all." },
  ];

  // ---- Taxonomies ---------------------------------------------------------------
  const pythonTopics = [
    ["Values and types", ["Integers and floats", "Strings as values", "Type conversion", "Booleans"]],
    ["Variables and expressions", ["Assignment", "Operator precedence", "Augmented assignment", "Naming rules"]],
    ["Conditionals", ["if / elif / else", "Comparison operators", "Logical operators", "Nested conditionals"]],
    ["Loops", ["while loops", "range() and counted loops", "break and continue", "Loop accumulators"]],
    ["Functions", ["Defining functions", "Parameters and arguments", "Return values", "Scope"]],
    ["Strings", ["String indexing", "Slicing", "String methods", "f-strings"]],
    ["Lists", ["List indexing", "List methods", "Aliasing", "List comprehensions"]],
    ["Dictionaries", ["Keys and values", "Iterating a dict", "Counting with dicts", "Nested dicts"]],
    ["Tuples and sets", ["Tuple packing", "Immutability", "Set operations", "Choosing a collection"]],
    ["Files", ["Reading files", "Writing files", "with statements", "Parsing lines"]],
    ["Exceptions", ["try / except", "Raising errors", "Common error types", "finally"]],
    ["Classes", ["Defining a class", "Attributes", "Methods", "__init__"]],
  ];
  const statsTopics = [
    ["Describing data", ["Types of variables", "Measures of center", "Measures of spread", "Outliers"]],
    ["Probability", ["Sample spaces", "Addition rule", "Conditional probability", "Independence"]],
    ["Random variables", ["Discrete distributions", "Expected value", "Binomial distribution", "Variance"]],
    ["Normal distribution", ["z-scores", "Empirical rule", "Normal approximation"]],
    ["Sampling distributions", ["Central limit theorem", "Standard error", "Sampling bias"]],
    ["Confidence intervals", ["Interval for a mean", "Interval for a proportion", "Margin of error"]],
    ["Hypothesis tests", ["Null and alternative", "p-values", "Type I and II errors", "One-sample t-test"]],
    ["Regression", ["Scatterplots and correlation", "Least-squares line", "Residuals"]],
  ];

  let subId = 1;
  const buildTaxonomy = (topics, prefix) =>
    topics.map(([name, subs], i) => ({
      id: `${prefix}-t${i + 1}`,
      name,
      subtopics: subs.map((s) => ({
        id: subId++,
        name: s,
        description: `What a student should be able to do with ${s.toLowerCase()}.`,
      })),
    }));

  const pyTaxonomy = buildTaxonomy(pythonTopics, "py");
  const statsDraft = buildTaxonomy(statsTopics, "st");
  // AI draft: each row carries a review state and the book section it was drafted from.
  statsDraft.forEach((t, i) => {
    t.draft_state = i < 3 ? "accepted" : "proposed";
    t.source = `OpenIntro Statistics, ch. ${i + 1}`;
    t.subtopics.forEach((s, j) => {
      s.draft_state = i < 3 ? "accepted" : j === 2 && i === 5 ? "flagged" : "proposed";
      s.confidence = pick(["high", "high", "medium", "low"]);
    });
  });
  // A 4th Regression subtopic (29 in all), appended after the loop so the seeded rand stream,
  // and with it every question below, stays unchanged.
  statsDraft[7].subtopics.push({ id: subId++, name: "Interpreting the slope",
    description: "What a student should be able to do with interpreting the slope.", draft_state: "proposed", confidence: "medium" });

  // ---- Books --------------------------------------------------------------------
  const books = [
    {
      id: "b1", course: "python", title: "Think Python, 3rd ed.", authors: "Allen B. Downey",
      format: "book_pdf", status: "imported", chapters: 19, sections: 212, embedded: 212,
      structure_source: "pdf_outline", confidence: "high", uploaded: "2026-08-18", warnings: [],
    },
    {
      id: "b2", course: "python", title: "Python for Everybody", authors: "Charles Severance",
      format: "book_json", status: "partial", chapters: 16, sections: 148, embedded: 148,
      structure_source: "structured_json", confidence: "high", uploaded: "2026-08-20",
      warnings: [{ severity: "info", code: "no_page_numbers", text: "The document has no page numbers; citations show section only." }],
    },
    {
      id: "b3", course: "statistics", title: "OpenIntro Statistics, 4th ed.", authors: "Diez, Çetinkaya-Rundel, Barr",
      format: "book_pdf", status: "imported", chapters: 9, sections: 64, embedded: 41,
      structure_source: "pdf_outline", confidence: "high", uploaded: "2026-09-27", warnings: [],
    },
  ];

  const sectionTitles = {
    b1: [
      ["1", "Programming as a way of thinking", ["1.1 Arithmetic operators", "1.2 Expressions", "1.3 Arithmetic functions", "1.4 Strings", "1.5 Values and types"]],
      ["2", "Variables and statements", ["2.1 Variables", "2.2 State diagrams", "2.3 Variable names", "2.4 The import statement"]],
      ["7", "Iteration and search", ["7.1 Loops and strings", "7.2 Reading the word list", "7.3 Updating variables", "7.4 Looping and counting", "7.5 The in operator"]],
      ["9", "Lists", ["9.1 A list is a sequence", "9.2 Lists are mutable", "9.3 List slices", "9.10 Objects and values", "9.11 Aliasing"]],
    ],
  };
  const books_sections = {};
  Object.entries(sectionTitles).forEach(([bid, chapters]) => {
    books_sections[bid] = chapters.map(([num, title, secs]) => ({
      number: num, title,
      sections: secs.map((s, k) => ({
        id: `${bid}-${num}-${k + 1}`, title: s, confidence: k === 3 && num === "7" ? "medium" : "high",
        words: 400 + Math.floor(rand() * 2200), questions: Math.floor(rand() * 6),
      })),
    }));
  });
  const sampleSectionText = [
    "Variables refer to objects. If a and b refer to the same list, a change made through one name is visible through the other. We say the list is aliased.",
    "a = [1, 2, 3]\nb = a\nb[0] = 42\nprint(a)   # [42, 2, 3]",
    "Aliasing is useful, but it can be surprising. In general it is safer to avoid aliasing when you are working with mutable objects. To make a copy, use the slice operator: c = a[:].",
  ];

  // ---- Questions ------------------------------------------------------------------
  const qTemplates = [
    { type: "multiple_choice", prompt: "What does print(a) show after `b = a; b[0] = 42` when a = [1, 2, 3]?", options: ["[1, 2, 3]", "[42, 2, 3]", "[42]", "An error"], answer: 1, sub: "Aliasing", topic: "Lists" },
    { type: "output_prediction", prompt: "What is printed?\n\nfor i in range(1, 10, 3):\n    print(i, end=' ')", answer_text: "1 4 7", sub: "range() and counted loops", topic: "Loops" },
    { type: "parsons", prompt: "Put the lines in order so the function returns the sum of the even numbers in a list.", lines: ["def sum_even(nums):", "    total = 0", "    for n in nums:", "        if n % 2 == 0:", "            total += n", "    return total"], sub: "Loop accumulators", topic: "Loops" },
    { type: "code_completion", prompt: "Complete the function so it returns the word with its first letter capitalised.\n\ndef cap(word):\n    return ____", answer_text: "word[0].upper() + word[1:]", sub: "Slicing", topic: "Strings" },
    { type: "true_false", prompt: "A dictionary key can be a list.", answer: false, sub: "Keys and values", topic: "Dictionaries" },
    { type: "debugging", prompt: "This loop never ends. Fix it.\n\ni = 0\nwhile i < 5:\n    print(i)", answer_text: "Add `i += 1` inside the loop.", sub: "while loops", topic: "Loops" },
    { type: "multiple_choice", prompt: "Which expression evaluates to True?", options: ["3 > 5 or 2 > 4", "not (1 == 1)", "5 > 2 and 2 >= 2", "'a' == 'A'"], answer: 2, sub: "Logical operators", topic: "Conditionals" },
    { type: "multiple_choice", prompt: "What is the value of `len(\"hello\"[1:4])`?", options: ["2", "3", "4", "5"], answer: 1, sub: "Slicing", topic: "Strings" },
    { type: "coding", prompt: "Write count_words(text) that returns a dict mapping each word to how many times it appears.", answer_text: "Tests: 4 cases, including empty string.", sub: "Counting with dicts", topic: "Dictionaries" },
    { type: "multiple_choice", prompt: "What happens when a function has no return statement?", options: ["It returns 0", "It returns None", "It raises an error", "It returns the last value computed"], answer: 1, sub: "Return values", topic: "Functions" },
    { type: "output_prediction", prompt: "What is printed?\n\nx = 10\ndef f():\n    x = 5\nf()\nprint(x)", answer_text: "10", sub: "Scope", topic: "Functions" },
    { type: "multiple_choice", prompt: "Which statement opens a file so it is closed automatically?", options: ["open('f.txt')", "with open('f.txt') as f:", "file('f.txt')", "open('f.txt').close()"], answer: 1, sub: "with statements", topic: "Files" },
  ];
  // Later copies of each template vary the code and values, so the 60-question bank doesn't
  // repeat the same 12 stems. Question i uses VARIANTS[i % 12][k - 1] when k = floor(i / 12) >= 1.
  const VARIANTS = [
    [
      { prompt: "What does print(a) show after `b = a; b.append(7)` when a = [5, 6]?", options: ["[5, 6]", "[5, 6, 7]", "[7]", "An error"], answer: 1 },
      { prompt: "What does print(a) show after `b = a[:]; b[0] = 0` when a = [3, 4, 5]?", options: ["[0, 4, 5]", "[3, 4, 5]", "[0]", "An error"], answer: 1 },
      { prompt: "After `x = [1, 2]; y = x; y += [3]`, what is `x`?", options: ["[1, 2]", "[1, 2, 3]", "[3]", "[1, 2, [3]]"], answer: 1 },
      { prompt: "Which line makes `b` an independent copy of the list `a`?", options: ["b = a", "b = a[:]", "b == a", "b = [a]"], answer: 1 },
    ],
    [
      { prompt: "What is printed?\n\nfor i in range(10, 0, -4):\n    print(i, end=' ')", answer_text: "10 6 2" },
      { prompt: "What is printed?\n\nfor i in range(3):\n    print(i * 2, end=' ')", answer_text: "0 2 4" },
      { prompt: "What is printed?\n\nprint(list(range(2, 12, 4)))", answer_text: "[2, 6, 10]" },
      { prompt: "What is printed?\n\nprint(len(range(5, 20, 5)))", answer_text: "3" },
    ],
    [
      { prompt: "Put the lines in order so the function returns how many words in a list are longer than 3 letters.", lines: ["def count_long(words):", "    count = 0", "    for w in words:", "        if len(w) > 3:", "            count += 1", "    return count"] },
      { prompt: "Put the lines in order so the function returns the largest number in a non-empty list.", lines: ["def largest(nums):", "    best = nums[0]", "    for n in nums:", "        if n > best:", "            best = n", "    return best"] },
      { prompt: "Put the lines in order so the function returns the product of a list of numbers.", lines: ["def product(nums):", "    result = 1", "    for n in nums:", "        result *= n", "    return result"] },
      { prompt: "Put the lines in order so the function returns a new list with only the negative numbers.", lines: ["def negatives(nums):", "    out = []", "    for n in nums:", "        if n < 0:", "            out.append(n)", "    return out"] },
    ],
    [
      { prompt: "Complete the function so it returns the last three characters of s.\n\ndef tail(s):\n    return ____", answer_text: "s[-3:]" },
      { prompt: "Complete the function so it returns s reversed.\n\ndef rev(s):\n    return ____", answer_text: "s[::-1]" },
      { prompt: "Complete the function so it returns s without its first and last character.\n\ndef inner(s):\n    return ____", answer_text: "s[1:-1]" },
      { prompt: "Complete the function so it returns every second character of s, starting with the first.\n\ndef evens(s):\n    return ____", answer_text: "s[::2]" },
    ],
    [
      { prompt: "A tuple of numbers can be used as a dictionary key.", answer: true },
      { prompt: "Assigning to an existing key in a dictionary adds a second entry with that key.", answer: false },
      { prompt: "`d.get('x')` raises a KeyError when 'x' is not a key of d.", answer: false },
      { prompt: "`'a' in d` checks the keys of d, not its values.", answer: true },
    ],
    [
      { prompt: "This loop should print 5, 4, 3, 2, 1 but never ends. Fix it.\n\nn = 5\nwhile n > 0:\n    print(n)\n    n += 1", answer_text: "Change `n += 1` to `n -= 1`." },
      { prompt: "This loop should stop when the user types 'q' but never does. Fix it.\n\ncmd = ''\nwhile cmd != 'q':\n    print('running')", answer_text: "Read `cmd = input()` inside the loop." },
      { prompt: "This loop should print 0 to 4 but prints nothing. Fix it.\n\ni = 0\nwhile i > 5:\n    print(i)\n    i += 1", answer_text: "Change the condition to `i < 5`." },
      { prompt: "This loop should add up 1 to 10 but gives 45. Fix it.\n\ntotal, i = 0, 1\nwhile i < 10:\n    total += i\n    i += 1", answer_text: "Use `i <= 10`." },
    ],
    [
      { prompt: "Which expression evaluates to False?", options: ["not False", "3 == 3 and 4 > 1", "0 or 1", "10 < 5 or 2 == 3"], answer: 3 },
      { prompt: "What is the value of `True and not (2 > 3)`?", options: ["True", "False", "None", "An error"], answer: 0 },
      { prompt: "For x = 7, which condition is True?", options: ["x > 5 and x < 7", "x % 2 == 0", "x >= 7 and x != 8", "not x > 3"], answer: 2 },
      { prompt: "What does `print(5 > 3 or 1 / 0)` do?", options: ["Prints True", "Raises ZeroDivisionError", "Prints False", "Prints 1"], answer: 0 },
    ],
    [
      { prompt: "What is the value of `\"python\"[2:]`?", options: ["\"py\"", "\"thon\"", "\"ython\"", "\"t\""], answer: 1 },
      { prompt: "What is the value of `\"banana\"[-2]`?", options: ["\"n\"", "\"a\"", "\"na\"", "\"b\""], answer: 0 },
      { prompt: "What is the value of `len(\"data\"[1:])`?", options: ["1", "2", "3", "4"], answer: 2 },
      { prompt: "What is the value of `\"abcdef\"[::3]`?", options: ["\"ad\"", "\"abc\"", "\"cf\"", "\"adf\""], answer: 0 },
    ],
    [
      { prompt: "Write letter_counts(word) that returns a dict mapping each letter to how many times it appears.", answer_text: "Tests: 5 cases, including repeated letters and an empty word." },
      { prompt: "Write most_common(words) that returns the word that appears most often in a list.", answer_text: "Tests: 4 cases, including a tie broken by first appearance." },
      { prompt: "Write invert(d) that returns a new dict with the keys and values of d swapped.", answer_text: "Tests: 3 cases, including an empty dict." },
      { prompt: "Write histogram(nums) that returns a dict mapping each number to its count.", answer_text: "Tests: 4 cases, including negative numbers." },
    ],
    [
      { prompt: "What does `print(f(3))` show?\n\ndef f(x):\n    x * 2", options: ["6", "None", "3", "An error"], answer: 1 },
      { prompt: "What does `return a, b` give back to the caller?", options: ["Two separate values", "One tuple", "One list", "Only a"], answer: 1 },
      { prompt: "What happens to code after a `return` statement in the same block?", options: ["It runs after the return", "It never runs", "It raises an error", "It runs only once"], answer: 1 },
      { prompt: "What does `print(g())` show?\n\ndef g():\n    return", options: ["0", "An empty line", "None", "An error"], answer: 2 },
    ],
    [
      { prompt: "What is printed?\n\ncount = 0\ndef add():\n    global count\n    count += 1\nadd(); add()\nprint(count)", answer_text: "2" },
      { prompt: "What is printed?\n\ndef f(n):\n    n = n + 1\n    return n\nn = 3\nf(n)\nprint(n)", answer_text: "3" },
      { prompt: "What is printed?\n\nx = 'outer'\ndef f():\n    print(x)\nf()", answer_text: "outer" },
      { prompt: "What is printed?\n\ndef f(items):\n    items.append(1)\nxs = []\nf(xs)\nprint(xs)", answer_text: "[1]" },
    ],
    [
      { prompt: "What does the mode 'a' in `open('log.txt', 'a')` do?", options: ["Reads the file", "Appends to the end", "Replaces the file", "Opens as binary"], answer: 1 },
      { prompt: "After a `with open('f.txt') as f:` block ends, what state is f in?", options: ["Still open", "Closed", "Deleted", "Empty"], answer: 1 },
      { prompt: "Which call reads the whole file into one string?", options: ["f.readline()", "f.read()", "f.readlines()", "list(f)"], answer: 1 },
      { prompt: "What does opening an existing file with mode 'w' do to its contents?", options: ["Keeps them", "Erases them", "Appends to them", "Raises an error"], answer: 1 },
    ],
  ];
  const SOURCE_BY_TOPIC = {
    Lists: "9.11 Aliasing", Loops: "7.3 Updating variables", Strings: "8.4 String slices",
    Dictionaries: "10.2 Dictionaries as collections of counters", Conditionals: "5.2 Boolean expressions",
    Functions: "6.1 Return values", Files: "14.3 Reading and writing",
  };
  const statuses = ["generated", "validation_passed", "validation_passed", "validation_passed", "approved", "approved", "approved", "rejected", "validation_failed"];
  const findSub = (name) => {
    for (const t of pyTaxonomy) for (const s of t.subtopics) if (s.name === name) return { topic: t, sub: s };
    return { topic: pyTaxonomy[0], sub: pyTaxonomy[0].subtopics[0] };
  };
  const questions = [];
  for (let i = 0; i < 60; i++) {
    const k = Math.floor(i / qTemplates.length);
    const tpl = { ...qTemplates[i % qTemplates.length], ...(k ? VARIANTS[i % qTemplates.length][(k - 1) % 4] : {}) };
    const { topic, sub } = findSub(tpl.sub);
    const status = i < 12 ? "validation_passed" : pick(statuses);
    const verdict = () => pick(["pass", "pass", "pass", "flag"]);
    questions.push({
      id: 1000 + i, course: "python", type: tpl.type, prompt: tpl.prompt, options: tpl.options || null,
      answer: tpl.answer ?? null, answer_text: tpl.answer_text || null, lines: tpl.lines || null,
      topic_id: topic.id, topic: topic.name, subtopic_id: sub.id, subtopic: sub.name,
      difficulty: pick(["easy", "medium", "medium", "hard"]), status,
      source: { book: "Think Python, 3rd ed.", section: SOURCE_BY_TOPIC[topic.name] || "1.5 Values and types" },
      checks: { schema: "pass", answer_consistency: status === "validation_failed" ? "fail" : "pass", runs: QUESTION_TYPES[tpl.type].code ? (status === "validation_failed" ? "fail" : "pass") : "n/a" },
      judges: { issues: verdict(), subtopic: verdict(), difficulty: verdict(), generatability: "pass" },
      judge_notes: "Distractor 3 is implausible for this level; consider an off-by-one alternative.",
      possible_duplicate_of: i >= qTemplates.length && i % 5 === 0 ? [{ question_id: 1000 + i - qTemplates.length, score: 0.91 }] : [],
      rejection_reason: status === "rejected" ? pick(REJECTION_REASONS)[0] : null,
      created: `2026-09-${String(10 + (i % 18)).padStart(2, "0")}`, generator: "run-" + (40 + Math.floor(i / 8)),
      history: [{ at: `2026-09-${String(10 + (i % 18)).padStart(2, "0")} 10:14`, who: "Generator", what: `Created from section ${(SOURCE_BY_TOPIC[topic.name] || "1.5").split(" ")[0]}` }],
    });
  }

  // ---- Coverage: count of approved questions per subtopic x difficulty ------------
  const TARGET = 2;
  const coverage = {};
  pyTaxonomy.forEach((t) => t.subtopics.forEach((s) => {
    coverage[s.id] = { easy: 0, medium: 0, hard: 0 };
  }));
  questions.filter((q) => q.status === "approved").forEach((q) => { coverage[q.subtopic_id][q.difficulty]++; });
  // Spread some extra approved counts so the grid isn't mostly empty (mock only).
  Object.values(coverage).forEach((c) => {
    ["easy", "medium", "hard"].forEach((d) => { if (rand() < 0.7) c[d] += 2 + Math.floor(rand() * 2); else if (rand() < 0.5) c[d] += 1; });
  });
  const cells = Object.values(coverage).flatMap((c) => [c.easy, c.medium, c.hard]);
  const coveragePct = Math.round((100 * cells.filter((n) => n >= TARGET).length) / cells.length);

  // ---- Students -------------------------------------------------------------------
  const first = ["Aisha", "Ben", "Carla", "Dev", "Elena", "Farid", "Grace", "Hiro", "Ines", "Jamal", "Kira", "Liam", "Mei", "Noah", "Olu", "Priya", "Quinn", "Rosa", "Sam", "Tariq", "Uma", "Victor", "Wen", "Ximena", "Yusuf", "Zoe", "Arjun", "Beatriz"];
  const last = ["Okafor", "Nguyen", "Silva", "Patel", "Kowalski", "Haddad", "Kim", "Tanaka", "Moreau", "Brown", "Ivanova", "Walsh", "Lin", "Garcia", "Adeyemi", "Rao", "Murphy", "Diaz", "Cohen", "Aziz", "Shah", "Petrov", "Zhou", "Lopez", "Demir", "Fischer", "Menon", "Costa"];
  const students = first.map((f, i) => {
    const mastery = {};
    pyTaxonomy.forEach((t, k) => {
      const base = Math.max(0.05, Math.min(0.97, 0.9 - k * 0.07 + (rand() - 0.5) * 0.5));
      mastery[t.id] = round2(k > 7 && i % 3 ? 0 : base);
    });
    const vals = Object.values(mastery).filter((v) => v > 0);
    return {
      id: `s${i + 1}`, name: `${f} ${last[i]}`, email: `${f.toLowerCase()}.${last[i].toLowerCase()}@example.edu`,
      class_id: i < 16 ? "c1" : "c2", course: "python",
      sessions: 2 + Math.floor(rand() * 14), attempts: 20 + Math.floor(rand() * 180),
      last_active: `2026-09-${String(14 + Math.floor(rand() * 16)).padStart(2, "0")}`,
      mastery, avg_mastery: round2(vals.reduce((a, b) => a + b, 0) / vals.length),
      trend: Array.from({ length: 8 }, (_, w) => round2(Math.min(0.95, 0.2 + w * 0.07 + (rand() - 0.5) * 0.1))),
      weak_subtopics: [pick(pyTaxonomy[3].subtopics).name, pick(pyTaxonomy[6].subtopics).name],
    };
  });

  // ---- Courses --------------------------------------------------------------------
  const courses = [
    {
      id: "python", code: "CS 135", name: "Intro to Python", term: "Fall 2026", subject: "python",
      question_types: SUBJECTS[0].types, owner: "u1", collaborators: ["u2"],
      taxonomy: pyTaxonomy, taxonomy_versions: [
        { id: "v3", label: "v3 — added Classes", status: "approved", active: true, topics: 12, subtopics: 48, created: "2026-09-02", source: "Built by hand" },
        { id: "v2", label: "v2", status: "superseded", active: false, topics: 11, subtopics: 44, created: "2026-08-25", source: "Imported JSON" },
        { id: "v1", label: "v1", status: "superseded", active: false, topics: 9, subtopics: 31, created: "2026-08-19", source: "Imported JSON" },
      ],
      coverage_target: TARGET,
      // Setup steps drive the course sidebar badges and the overview checklist.
      setup: { materials: "done", taxonomy: "done", coverage: "in_progress", review: "in_progress", question_set: "done", classes: "done" },
      numbers: {
        questions: questions.length,
        approved: questions.filter((q) => q.status === "approved").length,
        awaiting_review: questions.filter((q) => q.status === "validation_passed").length,
        students: students.length,
        avg_mastery: round2(students.reduce((a, st) => a + st.avg_mastery, 0) / students.length),
        coverage_pct: coveragePct,
      },
    },
    {
      id: "statistics", code: "STAT 152", name: "Intro Statistics", term: "Fall 2026", subject: "statistics",
      question_types: SUBJECTS[1].types, owner: "u1", collaborators: [],
      taxonomy: [], taxonomy_draft: statsDraft, taxonomy_versions: [
        { id: "d1", label: "AI draft from OpenIntro Statistics", status: "under_review", active: false, topics: 8, subtopics: 29, created: "2026-09-28", source: "Drafted with AI" },
      ],
      coverage_target: TARGET,
      setup: { materials: "done", taxonomy: "in_progress", coverage: "todo", review: "todo", question_set: "todo", classes: "todo" },
      numbers: { questions: 0, approved: 0, awaiting_review: 0, students: 0, avg_mastery: null, coverage_pct: 0 },
    },
  ];

  const question_sets = [
    { id: "qs2", course: "python", name: "Midterm practice", frozen: "2026-09-20", questions: 23, coverage_pct: 71, classes: ["c1", "c2"], status: "published" },
    { id: "qs1", course: "python", name: "Weeks 1–3", frozen: "2026-09-05", questions: 14, coverage_pct: 38, classes: [], status: "archived" },
  ];
  const classes = [
    { id: "c1", course: "python", name: "Section 001 (Mon/Wed)", join_code: "PY7-K4Q", question_set: "qs2", students: 16, restrict_roster: false, created: "2026-09-06" },
    { id: "c2", course: "python", name: "Section 002 (Tue/Thu)", join_code: "PY7-M2X", question_set: "qs2", students: 12, restrict_roster: true, created: "2026-09-06" },
  ];

  const jobs = [
    { id: "j9", course: "python", kind: "Generate for gaps", detail: "Loops · 6 cells", status: "running", progress: 0.62, started: "2 min ago", by: "Maya Chen" },
    { id: "j8", course: "statistics", kind: "Embed book", detail: "OpenIntro Statistics · 64 sections", status: "running", progress: 0.64, started: "4 min ago", by: "Maya Chen" },
    { id: "j7", course: "statistics", kind: "Draft taxonomy with AI", detail: "OpenIntro Statistics", status: "done", progress: 1, started: "Sep 28, 14:02", by: "Maya Chen", result: "8 topics, 29 subtopics" },
    { id: "j6", course: "python", kind: "Re-run judges", detail: "42 questions", status: "failed", progress: 0.4, started: "Sep 27, 09:40", by: "Maya Chen", error: "LLM provider returned 429 (rate limited) after 17 of 42. The 17 results were kept." },
    { id: "j5", course: "python", kind: "Import book", detail: "Python for Everybody", status: "done", progress: 1, started: "Aug 20, 11:15", by: "Maya Chen", result: "148 sections, 1 info warning" },
  ];

  const usage = {
    month: "September 2026", cap_usd: 50, spent_usd: 41.3,
    by_course: [
      { course: "python", spent_usd: 33.9, calls: 2140, tokens_m: 11.2 },
      { course: "statistics", spent_usd: 7.4, calls: 310, tokens_m: 2.6 },
    ],
    by_kind: [["Question generation", 21.6], ["Judges", 12.1], ["Taxonomy drafting", 3.2], ["Embeddings", 0.9], ["Re-runs", 3.5]],
    daily: Array.from({ length: 30 }, (_, d) => round2(0.4 + rand() * 2.6)),
  };

  const alignment = {
    course: "python",
    // Agreement between each judge's verdict and the professor's first review (ADR-029/034).
    judges: [
      { id: "issues", agreement: 0.84, reviews: 118, trend: [0.71, 0.75, 0.79, 0.84] },
      { id: "subtopic", agreement: 0.91, reviews: 118, trend: [0.86, 0.88, 0.9, 0.91] },
      { id: "difficulty", agreement: 0.67, reviews: 118, trend: [0.61, 0.63, 0.66, 0.67] },
      { id: "generatability", agreement: 0.95, reviews: 118, trend: [0.93, 0.94, 0.95, 0.95] },
    ],
    learned_rules: [
      { id: "r1", type: "multiple_choice", text: "Distractors must be plausible mistakes a beginner makes (off-by-one, aliasing confusion), not unrelated values.", from_reviews: 9, enabled: true, created: "2026-09-10" },
      { id: "r2", type: "output_prediction", text: "Keep snippets under 8 lines; avoid print formatting tricks that test end= rather than the concept.", from_reviews: 5, enabled: true, created: "2026-09-14" },
      { id: "r3", type: "parsons", text: "Include exactly one distractor line only for medium and hard questions.", from_reviews: 4, enabled: false, created: "2026-09-18" },
      { id: "r4", type: "multiple_choice", text: "Do not use 'All of the above' or 'None of the above'.", from_reviews: 6, enabled: true, created: "2026-09-21" },
    ],
    approval_rate_trend: [0.48, 0.55, 0.61, 0.66, 0.72],
  };

  const users = [
    { id: "u1", name: "Maya Chen", email: "maya.chen@example.edu", role: "Owner", initials: "MC" },
    { id: "u2", name: "Daniel Ortiz", email: "d.ortiz@example.edu", role: "Co-instructor", initials: "DO" },
  ];

  // The demo student (s5) practises Loops and Lists, so those must be weak topics for them.
  Object.assign(students[4].mastery, { "py-t4": 0.41, "py-t7": 0.52 });
  {
    const vals = Object.values(students[4].mastery).filter((v) => v > 0);
    students[4].avg_mastery = round2(vals.reduce((a, b) => a + b, 0) / vals.length);
    students[4].weak_subtopics = ["Aliasing", "List comprehensions"]; // same as their own home page (data-f.js)
    students[4].trend = [0.22, 0.29, 0.34, 0.41, 0.45, 0.5, 0.55, students[4].avg_mastery];
    courses[0].numbers.avg_mastery = round2(students.reduce((a, st) => a + st.avg_mastery, 0) / students.length);
  }

  // A student-side session: what the practice screen serves next.
  const student_session = {
    student: students[4], course: "python", class_id: "c1", question_set: "qs2",
    queue: questions.filter((q) => ["multiple_choice", "true_false", "output_prediction", "parsons"].includes(q.type)).slice(0, 6).map((q) => q.id),
    current_topic: "Lists", mastery_before: 0.52,
  };

  window.MOCK = {
    today: "2026-09-30", me: users[0], users, subjects: SUBJECTS, question_types: QUESTION_TYPES,
    judges: JUDGES, rejection_reasons: REJECTION_REASONS,
    courses, books, books_sections, sample_section_text: sampleSectionText,
    questions, coverage, students, question_sets, classes, jobs, usage, alignment, student_session,
    // Small helpers so pages don't reimplement lookups.
    course(id) { return courses.find((c) => c.id === id) || courses[0]; },
    question(id) { return questions.find((q) => q.id === Number(id)); },
    student(id) { return students.find((s) => s.id === id); },
    subject(id) { return SUBJECTS.find((s) => s.id === id); },
    judge(id) { return JUDGES.find((j) => j.id === id); },
  };
})();
