/*
 * Student lesson player (student-lesson.html) and lesson results (lesson-results.html).
 * Load after assets/lesson-schema.js (and data-lessons.js). Only ADDS to window.MOCK.
 *   MOCK.studentLesson(subId)  -> { sub, blocks, rich }   the lesson a student gets for a subtopic
 *   MOCK.lessonAsk             -> book-grounded answers for "Ask about this lesson"
 *   MOCK.lessonUsage(subId)    -> { students, opens } for the professor's lessons list
 *   MOCK.lessonResults(subId)  -> funnel, wrong answers, time and the holdout comparison
 * TODO(real): every number here is invented. Usage, funnel and wrong answers come from lesson
 * events; the holdout comparison from the randomized "no lesson" arm (1 in 5 misses).
 */
(function () {
  const M = window.MOCK;
  const RICH = M.RICH_LESSONS || {};

  // Small deterministic hash so invented numbers stay the same on every reload.
  const h = (n, salt = 0) => { let x = (Number(n) * 2654435761 + salt * 40503) % 4294967296; x = (x ^ (x >>> 13)) * 1274126177 % 4294967296; return (x >>> 0) / 4294967296; };

  // The lesson a student gets: the rich lesson when there is one, her hand-edited example,
  // otherwise the lesson generated in her style.
  M.studentLesson = (subId) => {
    const sub = M.lessonSub(subId) || M.lessonSub(27);
    if (RICH[sub.name]) return { sub, blocks: RICH[sub.name], rich: true };
    const own = M.lesson(sub.id);
    const blocks = own && own.status === "example" && own.blocks ? own.blocks : M.styledLesson(sub);
    return { sub, blocks, rich: false };
  };

  // ---- Ask about this lesson --------------------------------------------------------------
  // TODO(real): RAG over the course's embedded book sections; the answer must quote the passage
  // it is grounded in. Here: deterministic keyword match. Quotes marked (*) are invented wording.
  const TP = "Think Python, 3rd ed.";
  M.lessonAsk = {
    "Aliasing": {
      suggested: ["How do I copy a list?", "Does this happen with strings?", "What's the difference between is and ==?"],
      answers: [
        { keys: ["copy", "[:]", "slice", "separate", "list("], answer: "Make a new list with the same items: copy = groceries[:] uses a slice of the whole list. groceries.copy() and list(groceries) do the same thing. After that, changing copy leaves groceries alone.",
          quote: "To make a copy, use the slice operator: c = a[:].", section: "9.11 Aliasing" },
        { keys: ["string", "int", "number", "immutable", "tuple"], answer: "It happens, but it can't surprise you. Strings and numbers can't be changed in place, so there's no change for the second name to see. Aliasing only bites with things you can change, like lists and dicts.",
          quote: "In general it is safer to avoid aliasing when you are working with mutable objects.", section: "9.11 Aliasing" },
        { keys: [" is ", "==", "identical", "same object", "id("], answer: "a is b asks whether both names point at the same object; a == b asks whether the values are equal. After b = a both are True. After b = a[:] only == is True, because there are now two lists.",
          quote: "To check whether two variables refer to the same object, you can use the is operator.", section: "9.10 Objects and values", invented: true },
        { keys: ["both", "append", "same list", "shared", "point", "two names", "second name"], answer: "Because shared = groceries doesn't build a list. It makes shared refer to the list groceries already refers to. There is one list with two names, so append through either name changes that one list.",
          quote: "If a and b refer to the same list, a change made through one name is visible through the other.", section: "9.11 Aliasing" },
      ],
    },
    "range() and counted loops": {
      suggested: ["Why isn't stop included?", "Can range count backwards?", "Why does range(3) start at 0?"],
      answers: [
        { keys: ["backward", "negative", "down", "reverse", "-1"], answer: "Yes: give a negative step. range(10, 0, -2) gives 10, 8, 6, 4, 2. The fence still isn't crossed, so 0 is left out.",
          quote: "If the step is negative, the sequence counts down, and it still stops before the stop value.", section: "7.4 The range function", invented: true },
        { keys: ["zero", " 0", "start", "one number", "range(3)", "range(n)"], answer: "With one number, that number is the stop and the start defaults to 0. So range(3) is 0, 1, 2: three values, matching list indexes 0 to 2.",
          quote: "With a single argument, range starts at 0 and stops before the argument.", section: "7.4 The range function", invented: true },
        { keys: ["stop", "include", "last value", " 8", "fence"], answer: "Because range counts up to the stop value without reaching it. That way range(n) gives exactly n values, and range(len(xs)) gives every index of xs and no more.",
          quote: "The sequence goes up to, but does not include, the stop value.", section: "7.4 The range function", invented: true },
      ],
    },
  };
  // Fallback for lessons without hand-written answers: the lesson's idea, quoted from its book section.
  M.lessonAskFallback = (sub) => {
    const seed = (window.LESSON_SEEDS || {})[sub.name] || {};
    const section = (M.questions.find((q) => q.subtopic_id === sub.id)?.source.section) || "the course book";
    return {
      suggested: ["Can you explain it another way?", "Where is this in the book?"],
      answers: [
        { keys: ["another way", "explain", "again", "simpler", "don't get", "confus"], answer: `In one line: ${seed.idea || sub.name}. Try the worked example once more and change one value to see what moves.`, quote: seed.idea || "", section, invented: true },
        { keys: ["book", "where", "section", "read", "page"], answer: `It's covered in ${TP}, section ${section}. The lesson's worked example comes from there.`, quote: seed.idea || "", section, invented: true },
      ],
    };
  };
  M.lessonAskBook = TP;

  // ---- Professor side: usage and results --------------------------------------------------
  const enrolled = M.students.filter((s) => s.course === "python").length; // 28
  // Hand-set for her four example lessons; others derived from the hash. TODO(real).
  const USAGE = { 27: { students: 21, opens: 46 }, 14: { students: 17, opens: 29 }, 19: { students: 9, opens: 14 }, 29: { students: 6, opens: 8 } };
  M.lessonUsage = (subId) => {
    if (USAGE[subId]) return USAGE[subId];
    const students = 2 + Math.floor(h(subId, 1) * 8);
    return { students, opens: students + Math.floor(h(subId, 2) * students) };
  };
  M.lessonEnrolled = enrolled;

  // Per block: how many opens reached it, seconds spent, and wrong answers for interactive blocks.
  // Aliasing is written out; the rest are derived. TODO(real): from lesson block events.
  const ALIASING = {
    reached: [46, 45, 44, 37, 36, 35, 32, 32, 31, 31],          // predict … recap (h2 excluded)
    seconds: [34, 14, 52, 21, 12, 26, 38, 8, 19, 6],
    wrong: {
      predict: { first_try: 0.46, top: [["['eggs', 'milk']", 0.39], ["An error", 0.04], ["Something else", 0.03]] },
      branch: { first_try: 0.31, top: [["['eggs', 'milk']", 0.27], ["An error", 0.04]] },
      fill: { first_try: 0.22, top: [["groceries", 0.14], ["copy(groceries)", 0.05], ["Something else", 0.03]] },
      parsons: { first_try: 0.28, top: [["Used copy = groceries", 0.21], ["Wrong order", 0.07]] },
      check: { first_try: 0.19, top: [["[1, 2]", 0.15], ["[1, 2, [3]]", 0.04]] },
    },
    reports: [
      { at: "2026-09-29", block: "trace", text: "I couldn't tell which line had just run and which was next." },
      { at: "2026-09-24", block: "parsons", text: "Took me a while to see one line wasn't supposed to be used." },
    ],
    paths: { predict_right: 0.54, took_skip: 0.61, branch_missed: 0.31, replay_then_check_right: 0.71, no_replay_check_right: 0.84 },
  };
  // Randomized holdout: on a miss in practice, 1 in 5 students is not offered the lesson.
  // Outcome: correct on the next question on the same subtopic. Intent-to-treat (offered vs not).
  const HOLDOUT = {
    27: { offered: [44, 77], holdout: [8, 19], opened_of_offered: 34 / 77 },
    14: { offered: [31, 52], holdout: [6, 14], opened_of_offered: 0.40 },
    19: { offered: [19, 33], holdout: [4, 9], opened_of_offered: 0.30 },
    29: { offered: [11, 21], holdout: [3, 6], opened_of_offered: 0.29 },
  };
  // Pooled over the lessons that have a holdout (sums of the rows above).
  M.lessonHoldoutPooled = Object.values(HOLDOUT).reduce((a, x) => ({
    offered: [a.offered[0] + x.offered[0], a.offered[1] + x.offered[1]],
    holdout: [a.holdout[0] + x.holdout[0], a.holdout[1] + x.holdout[1]], lessons: a.lessons + 1,
  }), { offered: [0, 0], holdout: [0, 0], lessons: 0 });

  const firstTry = { predict: 0.4, branch: 0.3, fill: 0.25, parsons: 0.3, check: 0.22 };
  M.lessonResults = (subId) => {
    const { sub, blocks, rich } = M.studentLesson(subId);
    const steps = blocks.filter((b) => b.type !== "h2");
    const use = M.lessonUsage(sub.id);
    const hand = sub.name === "Aliasing" ? ALIASING : null;
    let left = use.opens;
    const rows = steps.map((b, k) => {
      if (hand) return { b, reached: hand.reached[k], seconds: hand.seconds[k] };
      if (k) left -= Math.round(h(sub.id, k + 10) * (b.type === "trace" || b.type === "example" ? 3 : 1.4));
      const secs = { predict: 30, explain: 15, example: 25, trace: 45, memory: 12, branch: 20, fill: 25, parsons: 35, explore: 30, mistake: 8, check: 18, recap: 6 }[b.type] || 10;
      return { b, reached: Math.max(1, left), seconds: Math.round(secs * (0.8 + h(sub.id, k) * 0.4)) };
    });
    const wrong = rows.filter((r) => firstTry[r.b.type] != null).map((r) => {
      const w = hand?.wrong[r.b.type] || null;
      let top = w ? w.top : [];
      if (!w && r.b.type === "check") {
        const wrongOpts = r.b.options.map((o, i) => [o, i]).filter(([, i]) => i !== r.b.answer);
        const share = firstTry.check * (0.7 + h(sub.id, 3) * 0.6);
        top = wrongOpts.map(([o], i) => [o, Math.round(share * (i === 0 ? 0.6 : 0.4 / Math.max(1, wrongOpts.length - 1)) * 100) / 100]).slice(0, 2);
      }
      return { b: r.b, n: r.reached, first_try: w ? w.first_try : Math.round(firstTry[r.b.type] * (0.7 + h(sub.id, 5) * 0.6) * 100) / 100, top };
    }).sort((a, b) => b.first_try - a.first_try);
    const hold = HOLDOUT[sub.id] || null;
    const total = rows.reduce((s, r) => s + r.seconds * (r.reached / use.opens), 0);
    return { sub, rich, use, rows, wrong, hold, enrolled,
      finished: rows[rows.length - 1]?.reached || 0, avg_seconds: Math.round(total), median_seconds: Math.round(total * 0.88),
      from_practice: hold ? Math.round(hold.offered[1] * hold.opened_of_offered) : Math.round(use.opens * 0.68), reports: hand?.reports || [], paths: hand?.paths || null };
  };
})();
