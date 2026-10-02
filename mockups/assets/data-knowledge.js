/*
 * Knowledge map: every subtopic is tagged with the KIND of thing it teaches and HOW its answers
 * are checked. The five kinds are the same in every subject (after the Knowledge-Learning-
 * Instruction framework: facts, categories, procedures, cause and effect, arguments).
 * Load after assets/data-knowledge-rules.js. TODO(real): kinds come from section analysis at import.
 */
(function () {
  const M = window.MOCK;
  M.KINDS = {
    fact: { label: "Fact", short: "Something to remember", ask: "fixed question → fixed answer",
      teach: ["Quick recall questions", "Spaced review"], checker: "lookup" },
    category: { label: "Category", short: "Telling cases apart", ask: "many cases → which group?",
      teach: ["Examples and non-examples", "Sort into groups", "Compare two cases"], checker: "lookup" },
    procedure: { label: "Procedure", short: "Steps to follow", ask: "input → steps → result",
      teach: ["Worked example", "Step-through", "Order the steps", "Fill the blank"], checker: "run" },
    model: { label: "Cause and effect", short: "How something behaves", ask: "if I change this, what happens?",
      teach: ["Predict, then see", "Sliders to explore", "Misconception check"], checker: "run" },
    argument: { label: "Argument", short: "Reasons and judgement", ask: "why? which is better?",
      teach: ["Compare two answers", "Write a short answer"], checker: "rubric" },
  };
  M.CHECKERS = {
    run: { label: "Run it", tone: "tone-ok", detail: "A program, formula or simulation works out the answer.", level: "Computed" },
    lookup: { label: "Look it up", tone: "tone-accent", detail: "A sentence in the book states the answer.", level: "Quoted" },
    rubric: { label: "Rubric", tone: "tone-warn", detail: "Graded against a rubric. Practice only.", level: "Rubric-graded" },
  };

  // The same five kinds in three subjects, using subtopics from the three mock courses.
  M.KIND_EXAMPLES = {
    fact: [["python", "Comparison operators", "== compares; = assigns"], ["statistics", "Types of variables", "A count is a discrete variable"], ["biology", "Organelles", "Mitochondria make most ATP"]],
    category: [["python", "Immutability", "Can this value be changed in place?"], ["statistics", "Sampling bias", "Is this sample biased or not?"], ["biology", "Prokaryotes and eukaryotes", "Prokaryote or eukaryote?"]],
    procedure: [["python", "range() and counted loops", "Trace what a loop prints"], ["statistics", "Interval for a mean", "Build a 95% confidence interval"], ["biology", "Punnett squares", "Work out a cross's offspring"]],
    model: [["python", "Aliasing", "Change b, and a changes too"], ["statistics", "Margin of error", "Bigger sample → narrower interval"], ["biology", "Membranes and transport", "Saltier outside → the cell shrinks"]],
    argument: [["python", "Choosing a collection", "Which collection fits this data, and why?"], ["statistics", "Null and alternative", "Does this study show causation?"], ["biology", "Enzymes", "Design an experiment on enzyme temperature"]],
  };

  // Kind of each Intro to Python subtopic. TODO(real): proposed at import, confirmed by the professor.
  const KIND_OF = {
    "Integers and floats": "model", "Strings as values": "model", "Type conversion": "procedure", "Booleans": "fact",
    "Assignment": "model", "Operator precedence": "procedure", "Augmented assignment": "procedure", "Naming rules": "fact",
    "if / elif / else": "procedure", "Comparison operators": "fact", "Logical operators": "procedure", "Nested conditionals": "procedure",
    "while loops": "procedure", "range() and counted loops": "procedure", "break and continue": "procedure", "Loop accumulators": "procedure",
    "Defining functions": "model", "Parameters and arguments": "procedure", "Return values": "model", "Scope": "model",
    "String indexing": "procedure", "Slicing": "procedure", "String methods": "model", "f-strings": "procedure",
    "List indexing": "procedure", "List methods": "model", "Aliasing": "model", "List comprehensions": "procedure",
    "Keys and values": "category", "Iterating a dict": "procedure", "Counting with dicts": "procedure", "Nested dicts": "procedure",
    "Tuple packing": "procedure", "Immutability": "category", "Set operations": "procedure", "Choosing a collection": "argument",
    "Reading files": "procedure", "Writing files": "procedure", "with statements": "model", "Parsing lines": "procedure",
    "try / except": "procedure", "Raising errors": "procedure", "Common error types": "category", "finally": "model",
    "Defining a class": "fact", "Attributes": "model", "Methods": "procedure", "__init__": "procedure",
  };
  // In Python, facts and categories can still be checked by running code ("is 2x a valid name?").
  const checkerFor = (kind) => (kind === "argument" ? "rubric" : "run");
  const extraRules = Object.fromEntries((M.wrong_rules || []).filter((w) => w.course === "python").map((w) => [w.sub, w.wrong.length]));
  M.knowledgeUnits = M.course("python").taxonomy.flatMap((t) => t.subtopics.map((s) => {
    const kind = KIND_OF[s.name] || "procedure";
    const written = extraRules[s.name] || (M.lessonMistake && M.lessonMistake[s.name] ? 1 : 0);
    return { sub_id: s.id, sub: s.name, topic: t.name, kind, checker: checkerFor(kind), wrong_rules: written,
      questions: M.questions.filter((q) => q.subtopic_id === s.id).length,
      lab: (M.wrong_rules || []).find((w) => w.sub === s.name)?.id || null };
  }));
})();
