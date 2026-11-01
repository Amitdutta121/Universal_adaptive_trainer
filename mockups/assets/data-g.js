/*
 * Shared mock data for the Phase 2 pages (G1–G11): the term schedule, assignments and each
 * student's status on them, student reports, class insights and exam holds.
 * Load right after assets/mock-data.js (and before any data-g-*.js). It only ADDS to window.MOCK.
 * TODO(real): every value in this file is invented.
 */
(function () {
  const M = window.MOCK;
  const py = M.course("python");
  const T = (name) => py.taxonomy.find((t) => t.name === name).id;

  // ---- G1 schedule -------------------------------------------------------------------
  // Fall 2026 runs Mon Aug 31 – Fri Dec 11; today (Sep 30) is in week 5.
  // A topic is practisable from the Monday of the week it is released.
  // The 8 topics released by week 5 are exactly the ones students have mastery on.
  const WEEK1 = new Date("2026-08-31T12:00:00");
  const weekStart = (w) => { const d = new Date(WEEK1); d.setDate(d.getDate() + (w - 1) * 7); return d; };
  const iso = (d) => d.toISOString().slice(0, 10);
  const plan = [
    [1, "Values, types and variables", ["Values and types", "Variables and expressions"]],
    [2, "Conditionals", ["Conditionals"]],
    [3, "Loops and functions", ["Loops", "Functions"]],
    [4, "Strings and lists", ["Strings", "Lists"]],
    [5, "Dictionaries", ["Dictionaries"]],
    [6, "Tuples and sets", ["Tuples and sets"]],
    [7, "Review", [], "Review week"],
    [8, "Midterm (Wed Oct 21)", [], "Midterm exam"],
    [9, "Files", ["Files"]],
    [10, "Exceptions", ["Exceptions"]],
    [11, "Classes I", ["Classes"]],
    [12, "Classes II", []],
    [13, "Project week", [], "Project"],
    [14, "Thanksgiving (no class Thu–Fri)", [], "Holiday"],
    [15, "Review", [], "Review week"],
  ];
  M.schedule = {
    python: {
      term: { name: "Fall 2026", starts: "2026-08-31", ends: "2026-12-11", final_exam: "2026-12-16" },
      release_mode: "schedule", // "schedule" | "all"
      current_week: 5,
      review_share: 0.2, // share of questions drawn from earlier weeks' topics
      weeks: plan.map(([week, title, topics, note]) => ({
        week, title, starts: iso(weekStart(week)), topics: topics.map(T), note: note || "",
      })),
    },
    statistics: null, // no approved taxonomy yet, so nothing to schedule
  };
  M.releasedTopics = (courseId, week) => {
    const s = M.schedule[courseId];
    if (!s) return [];
    const w = week ?? s.current_week;
    return s.weeks.filter((x) => x.week <= w).flatMap((x) => x.topics);
  };

  // ---- G2/G3 assignments ---------------------------------------------------------------
  // goal.type: "mastery" (reach target on each topic in scope) | "count" (answer n questions in scope)
  const A = (o) => ({ points: 10, sections: ["c1", "c2"], late: { days: 3, penalty: 0.2 }, lms: null, ...o });
  M.assignments = [
    A({ id: "a1", course: "python", name: "Week 2: Values, variables and conditionals", topics: [T("Values and types"), T("Variables and expressions"), T("Conditionals")],
        goal: { type: "mastery", target: 0.7 }, opens: "2026-09-07", due: "2026-09-11", status: "closed", lms: { synced: "2026-09-15 08:00" } }),
    A({ id: "a2", course: "python", name: "Week 3: Loops and functions", topics: [T("Loops"), T("Functions")],
        goal: { type: "mastery", target: 0.7 }, opens: "2026-09-14", due: "2026-09-18", status: "closed", lms: { synced: "2026-09-22 08:00" } }),
    A({ id: "a3", course: "python", name: "Week 4: Strings and lists", topics: [T("Strings"), T("Lists")],
        goal: { type: "mastery", target: 0.7 }, opens: "2026-09-21", due: "2026-09-25", status: "closed", lms: { synced: "2026-09-29 08:00" } }),
    A({ id: "a4", course: "python", name: "Week 5: Dictionaries", topics: [T("Dictionaries")],
        goal: { type: "mastery", target: 0.7 }, opens: "2026-09-28", due: "2026-10-02", status: "open", lms: { synced: null } }),
    A({ id: "a5", course: "python", name: "Week 6: Tuples and sets", topics: [T("Tuples and sets")],
        goal: { type: "mastery", target: 0.7 }, opens: "2026-10-05", due: "2026-10-09", status: "draft" }),
    A({ id: "a6", course: "python", name: "Midterm review", topics: M.releasedTopics("python", 6), points: 20,
        goal: { type: "count", n: 30 }, opens: "2026-10-12", due: "2026-10-20", status: "scheduled", late: { days: 0, penalty: 0 } }),
  ];
  M.assignment = (id) => M.assignments.find((a) => a.id === id);

  // Per-student notes and extensions (accommodations). TODO(real): entered by the instructor.
  M.student_notes = {
    s3: "Accommodation letter (Disability Resource Center): +3 days on practice deadlines.",
    s17: "Joined Sep 15 after adding the course; Week 2 excused.",
  };
  M.extensions = [
    { student: "s3", assignment: "a3", due: "2026-09-28", reason: "Accommodation letter" },
    { student: "s3", assignment: "a4", due: "2026-10-05", reason: "Accommodation letter" },
    { student: "s12", assignment: "a4", due: "2026-10-04", reason: "Illness, emailed Sep 29" },
  ];
  M.excused = [{ student: "s17", assignment: "a1" }];

  // Each student's result on each assignment, generated once here so the gradebook, student
  // detail, student home and digest agree. TODO(real): recorded by the server at the due date.
  let seed = 7;
  const rand = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;
    M.assignment_results = {};
  M.students.forEach((s) => {
    M.assignment_results[s.id] = {};
    M.assignments.forEach((a) => {
      const ext = M.extensions.find((e) => e.student === s.id && e.assignment === a.id);
      const r = { progress: 0, state: "not_started", score: null, submitted: null, extension: ext ? ext.due : null };
      if (M.excused.some((e) => e.student === s.id && e.assignment === a.id)) {
        Object.assign(r, { state: "excused", progress: 1 });
      } else if (a.status === "closed") {
        // Engaged students (higher average mastery) finish more often; a few are late or stop early.
        const x = rand();
        const pDone = 0.45 + 0.55 * s.avg_mastery;
        if (x < pDone) {
          const late = rand() < 0.12;
          Object.assign(r, { progress: 1, state: late ? "late" : "done", submitted: late ? "after due" : "on time",
            score: a.points * (late ? 1 - a.late.penalty : 1) });
        } else if (x < 0.95) {
          const pr = Math.round((0.35 + rand() * 0.55) * 100) / 100;
          Object.assign(r, { progress: pr, state: "partial", score: Math.round(a.points * pr * 10) / 10 });
        } else {
          Object.assign(r, { progress: 0, state: "missed", score: 0 });
        }
      } else if (a.status === "open") {
        const x = rand();
        if (x < 0.3) Object.assign(r, { progress: 1, state: "done", score: a.points, submitted: "on time" });
        else if (x < 0.78) Object.assign(r, { progress: Math.round((0.2 + rand() * 0.7) * 100) / 100, state: "in_progress" });
      }
      M.assignment_results[s.id][a.id] = r;
    });
  });
  // Elena (s5, the demo student) is mid-way through this week's assignment.
  Object.assign(M.assignment_results.s5.a4, { state: "in_progress", progress: 0.43 / 0.7, score: null });

  // ---- G7 student reports --------------------------------------------------------------
  // reason: answer_wrong | unclear | not_taught | typo
  M.reports = [
    { id: "r5", question_id: 1001, student: "s10", reason: "answer_wrong", at: "2026-09-29 21:14", status: "open",
      text: "I typed 1 4 7 with a space at the end and it was marked wrong.", answer: "1 4 7 " },
    { id: "r4", question_id: 1030, student: "s13", reason: "unclear", at: "2026-09-29 16:02", status: "open",
      text: "Does `not` happen before `and` here? We haven't covered precedence of not.", answer: "False" },
    { id: "r3", question_id: 1021, student: "s7", reason: "answer_wrong", at: "2026-09-28 10:47", status: "open",
      text: "f(3) is 6, so it prints 6. The answer key says None.", answer: "6" },
    { id: "r2", question_id: 1043, student: "s2", reason: "answer_wrong", at: "2026-09-23 19:30", status: "resolved",
      text: "\"data\"[1:] is 'ata', which is 3 letters. Marked wrong.", answer: "2",
      resolution: { action: "dismissed", by: "Daniel Ortiz", at: "2026-09-24 09:12", reply: "The key is 3 and it's accepted; your submitted answer was 2. Easy slip to make, though." } },
    { id: "r1", question_id: 1059, student: "s16", reason: "not_taught", at: "2026-09-14 11:05", status: "resolved",
      text: "We haven't done files yet.", answer: "Keeps them",
      resolution: { action: "schedule", by: "Maya Chen", at: "2026-09-14 13:40", reply: "You're right. Practice now follows the syllabus schedule; files open in week 9." } },
  ];
  M.REPORT_REASONS = { answer_wrong: "Answer marked wrong", unclear: "Question is unclear", not_taught: "Not taught yet", typo: "Typo or formatting" };

  // ---- G5 class insights (week 5, both sections) ----------------------------------------
  // TODO(real): aggregated from attempts; top_wrong is the most-picked wrong option or answer.
  M.insights = {
    python: {
      week: 5, range: "Sep 28 – Oct 4", students_active: 22, attempts: 1284, // 22 = students who started Week 5 (done + in progress)
      misconceptions: [
        { question_id: 1036, subtopic: "Aliasing", topic: "Lists", attempts: 55, correct: 0.51, top_wrong: "[1, 2]", top_wrong_share: 0.38,
          by_section: { c1: 0.33, c2: 0.45 }, reading: "Treats y = x as a copy of the list." },
        { question_id: 1016, subtopic: "Keys and values", topic: "Dictionaries", attempts: 61, correct: 0.54, top_wrong: "False", top_wrong_share: 0.41,
          by_section: { c1: 0.44, c2: 0.37 }, reading: "Thinks only strings and numbers can be keys." },
        { question_id: 1021, subtopic: "Return values", topic: "Functions", attempts: 47, correct: 0.6, top_wrong: "6", top_wrong_share: 0.34,
          by_section: { c1: 0.31, c2: 0.38 }, reading: "Expects the last expression to be returned without return." },
        { question_id: 1025, subtopic: "range() and counted loops", topic: "Loops", attempts: 48, correct: 0.63, top_wrong: "2 4 6", top_wrong_share: 0.31,
          by_section: { c1: 0.29, c2: 0.34 }, reading: "Starts range(3) at 1." },
        { question_id: 1043, subtopic: "Slicing", topic: "Strings", attempts: 44, correct: 0.66, top_wrong: "4", top_wrong_share: 0.29,
          by_section: { c1: 0.31, c2: 0.26 }, reading: "Doesn't drop the character before the start index." },
      ],
      improved: [
        { subtopic: "while loops", topic: "Loops", from: 0.48, to: 0.71 },
        { subtopic: "if / elif / else", topic: "Conditionals", from: 0.62, to: 0.8 },
      ],
      weekly_active: [23, 25, 24, 21, 22], // students who practised, weeks 1–5
    },
  };

  // ---- G8 exams and held questions -------------------------------------------------------
  M.exams = [
    { id: "e1", course: "python", name: "Midterm", date: "2026-10-21", exported: "2026-09-29", format: "Canvas (QTI 1.2)",
      questions: [1024, 1033, 1042, 1053, 1016, 1026], held_until: "2026-10-22" },
  ];
  M.heldFor = (qid) => M.exams.find((e) => e.questions.includes(qid)) || null;
})();
