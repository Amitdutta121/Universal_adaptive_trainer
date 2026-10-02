/*
 * Checking tools: the shared contract. A course's tools are the ways it can check answers. The
 * generator may write any question that one of the course's tools can check; every question records
 * the tool and version that checked it. Tools are added, paused or retired, never deleted.
 * Language runners include tests (there is no separate test runner).
 * Load right before assets/layout.js (after data-multi.js). It only ADDS to window.MOCK.
 * TODO(real): catalogue, versions, self-tests and per-course tool lists come from the backend.
 *
 *   MOCK.TOOL_CATALOG[id]   { id, name, checks, version, level, selftest: { ok, at, error? }, formats: [question formats it can check] }
 *   MOCK.course_tools[courseId]  [{ id, state: "on"|"paused"|"retired", added, by, calibration? }]
 *   MOCK.toolsFor(courseId)       catalogue entries joined with the course's state
 *   MOCK.checkedBy(q)             { tool, version, level }   which tool checked this question
 *   MOCK.toolForFormat(courseId, format)  the course tool that can check a format, or null
 *   MOCK.FORMAT_LABEL[format]     human label for a question format
 */
(function () {
  const M = window.MOCK;
  const T = (o) => ({ selftest: { ok: true, at: "2026-09-30 06:00" }, ...o });
  M.TOOL_CATALOG = {
    lookup: T({ id: "lookup", name: "Book lookup", version: "v2.1", level: "Quoted",
      checks: "Facts and definitions, by finding the sentence in the course book that states the answer.", formats: ["multiple_choice", "true_false", "short_text"] }),
    match: T({ id: "match", name: "Answer matcher", version: "v1.4", level: "AI-reviewed only",
      checks: "Multiple choice, ordering, matching and exact text against the key. The key itself is only reviewed by AI.", formats: ["multiple_choice", "true_false", "ordering", "matching", "short_text"] }),
    python: T({ id: "python", name: "Python runner", version: "v3.12-1", level: "Computed",
      checks: "Runs Python: works out what code prints, and runs hidden tests on code students write.", formats: ["output_prediction", "code_completion", "debugging", "parsons", "coding", "multiple_choice", "true_false"] }),
    numeric: T({ id: "numeric", name: "Numeric checker", version: "v1.1", level: "Computed",
      checks: "Numbers within a tolerance, with units, worked out by a short program.", formats: ["numeric", "multiple_choice"] }),
    maths: T({ id: "maths", name: "Maths engine", version: "v1.0", level: "Computed",
      checks: "Formulas: checks a student's expression is equivalent to the key (SymPy).", formats: ["expression", "numeric"] }),
    rubric: T({ id: "rubric", name: "Rubric grader", version: "v1.2", level: "Rubric-graded",
      checks: "Short written answers, graded criterion by criterion against a rubric you approve. Counts toward grades only once calibrated against your own grading.", formats: ["explanation"] }),
    sql: T({ id: "sql", name: "SQL engine", version: "v1.0", level: "Computed",
      checks: "Runs queries on a seeded database and compares the results.", formats: ["sql_query", "output_prediction", "multiple_choice"] }),
    web: T({ id: "web", name: "Web runner", version: "v1.0", level: "Computed",
      checks: "Loads HTML, CSS and JavaScript in a sandbox, clicks and types, and reads what's on screen.", formats: ["web_code", "output_prediction"] }),
    java: T({ id: "java", name: "Java runner", version: "v21-1", level: "Computed",
      checks: "Runs Java: output and hidden tests.", formats: ["output_prediction", "code_completion", "debugging", "coding"] }),
    logic: T({ id: "logic", name: "Logic checker", version: "v0.9", level: "Computed",
      checks: "Truth tables, equivalence and satisfiability (Z3).", formats: ["truth_table", "expression", "true_false"],
      selftest: { ok: false, at: "2026-09-30 06:00", error: "z3 solver not installed in the sandbox image" } }),
  };
  M.FORMAT_LABEL = {
    multiple_choice: "Multiple choice", true_false: "True / false", output_prediction: "Predict the output", code_completion: "Fill in the code",
    debugging: "Fix the bug", parsons: "Order the lines", coding: "Write a function", numeric: "Numeric answer", expression: "Formula",
    ordering: "Put in order", matching: "Matching", short_text: "Short answer", explanation: "Written explanation",
    sql_query: "Write a query", web_code: "Write HTML/CSS/JS", truth_table: "Truth table",
  };

  // Each course's tools. Order = order shown. TODO(real): stored per course; history is append-only.
  M.course_tools = {
    python: [
      { id: "lookup", state: "on", added: "2026-08-20", by: "Maya Chen" },
      { id: "match", state: "on", added: "2026-08-20", by: "Maya Chen" },
      { id: "python", state: "on", added: "2026-08-20", by: "Maya Chen" },
      { id: "numeric", state: "paused", added: "2026-09-02", by: "Daniel Ortiz", note: "Paused Sep 12: not needed after the floats unit." },
      { id: "rubric", state: "on", added: "2026-09-25", by: "Maya Chen",
        calibration: { graded: 14, needed: 20, agreement: 0.79, bar: 0.85, counts: false } },
    ],
    statistics: [
      { id: "lookup", state: "on", added: "2026-09-27", by: "Maya Chen" },
      { id: "match", state: "on", added: "2026-09-27", by: "Maya Chen" },
      { id: "numeric", state: "on", added: "2026-09-27", by: "Maya Chen" },
      { id: "maths", state: "on", added: "2026-09-27", by: "Maya Chen" },
      { id: "rubric", state: "on", added: "2026-09-27", by: "Maya Chen",
        calibration: { graded: 0, needed: 20, agreement: null, bar: 0.85, counts: false } },
    ],
    biology: [
      { id: "lookup", state: "on", added: "2026-08-22", by: "Maya Chen" },
      { id: "match", state: "on", added: "2026-08-22", by: "Maya Chen" },
      { id: "numeric", state: "on", added: "2026-08-22", by: "Maya Chen" },
      { id: "rubric", state: "on", added: "2026-09-01", by: "Maya Chen",
        calibration: { graded: 20, needed: 20, agreement: 0.88, bar: 0.85, counts: true } },
    ],
  };
  // Starting suggestions by subject for a new course (a label only; the professor picks the tools).
  M.TOOL_SUGGESTIONS = {
    python: ["lookup", "match", "python", "rubric"], statistics: ["lookup", "match", "numeric", "maths", "rubric"],
    physics: ["lookup", "match", "numeric", "maths", "rubric"], chemistry: ["lookup", "match", "numeric", "rubric"],
    biology: ["lookup", "match", "numeric", "rubric"], history: ["lookup", "match", "rubric"], general: ["lookup", "match", "rubric"],
  };

  M.toolsFor = (courseId) => (M.course_tools[courseId] || []).map((ct) => ({ ...M.TOOL_CATALOG[ct.id], ...ct }));
  M.toolForFormat = (courseId, format) => {
    const on = M.toolsFor(courseId).filter((t) => t.state === "on" && t.selftest.ok);
    const order = ["python", "java", "sql", "web", "numeric", "maths", "logic", "lookup", "match", "rubric"];
    return on.filter((t) => t.formats.includes(format)).sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id))[0] || null;
  };
  // Which tool checked a question: derived from how its key was verified (MOCK.verification).
  M.checkedBy = (q) => {
    if (!q) return null;
    const v = M.verification ? M.verification(q) : { level: "judged" };
    const code = M.question_types?.[q.type]?.code;
    let id = v.level === "proven" ? (q.course === "python" ? "python" : "numeric")
      : v.level === "supported" || v.level === "crosschecked" ? "lookup" : v.level === "rubric" ? "rubric" : "match";
    if (code) id = "python";
    const tool = M.TOOL_CATALOG[id];
    return { tool: id, name: tool.name, version: tool.version, level: tool.level, failed: !!v.failed };
  };
})();
