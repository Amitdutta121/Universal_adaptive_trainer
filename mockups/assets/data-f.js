/*
 * Extra mock data for the student pages (group F) and the landing page (A1).
 * Loaded right after mock-data.js; only ADDS fields to window.MOCK.
 * TODO(real): every value here is invented.
 */
(function () {
  const M = window.MOCK;
  const s = M.student_session;

  // TODO(real): explanations are written by the generator and approved with the question.
  // Keyed by question id (the six ids in MOCK.student_session.queue).
  const explanations = {
    1000: "b = a does not copy the list; it gives the same list a second name. Changing b[0] changes the one list both names refer to, so a shows [42, 2, 3]. To copy, use b = a[:].",
    1001: "range(1, 10, 3) starts at 1 and adds 3 while the value is below 10: 1, 4, 7. The next value, 10, is not included. end=' ' prints a space instead of a new line.",
    1002: "The total starts at 0 before the loop, is updated only inside the if, and is returned after the loop has finished, so return is indented at the function level.",
    1004: "Dictionary keys must be hashable. A list can change, so it cannot be a key; a tuple of the same values can.",
    1006: "5 > 2 is True and 2 >= 2 is True, so the and is True. The other three are False: both sides of the or are False, not (True) is False, and string comparison is case-sensitive.",
    1007: "\"hello\"[1:4] takes the characters at index 1, 2 and 3 — \"ell\" — because the stop index is not included. len(\"ell\") is 3.",
  };

  // TODO(real): the parsons line order a student is shown is shuffled by the server per attempt.
  const parsons_shuffle = { 1002: [2, 0, 5, 4, 1, 3] };

  // Each session opens with one warm-up the student is likely to get right, then goes to the
  // weakest subtopics. TODO(real): the selector picks the warm-up (easy, a topic above 70%).
  s.queue = [1007, ...s.queue.filter((id) => id !== 1007)];

  // Why the selector served this question (weakest subtopic first). TODO(real): from the selector's trace.
  const why = {
    1000: "Aliasing is your weakest subtopic (31%).",
    1001: "You missed a range() question last session.",
    1002: "Loop accumulators is below 50% for you.",
    1004: "You haven't practised Dictionaries yet in this set.",
    1006: "Logical operators is the weakest subtopic in Conditionals for you.",
    1007: "Warm-up: a quick one on Strings, which you know well.",
  };

  // Keep the student's Lists mastery consistent with the session's mastery_before.
  const listsTopic = M.courses[0].taxonomy.find((t) => t.name === "Lists");
  s.student.mastery[listsTopic.id] = s.mastery_before;

  // Per-subtopic mastery for the weakest-first list. TODO(real): from the BKT state per subtopic.
  const subtopic_mastery = {
    "Aliasing": 0.31, "Loop accumulators": 0.44, "Slicing": 0.46, "range() and counted loops": 0.49,
    "Logical operators": 0.53, "Keys and values": 0.38, "List comprehensions": 0.35, "Scope": 0.57,
  };

  M.student_extra = {
    explanations, parsons_shuffle, why, subtopic_mastery,
    // TODO(real): enrolments come from the student's join history.
    enrolments: [{ course: "python", class_id: "c1", joined: "2026-09-08", last_session: "2026-09-28", sessions: s.student.sessions }],
    instructor: "Dr. Maya Chen",
    // TODO(real): the server runs the BKT update (guess/slip/learn per subtopic). This stand-in
    // moves a topic's mastery 12% of the way up after a correct answer and 15% down after a wrong one,
    // so the practice and summary pages show the same numbers (Lists 52% -> 58% on a correct answer).
    update(m, correct) { return Math.round((correct ? m + 0.12 * (1 - m) : m - 0.15 * m) * 1000) / 1000; },
    // Replays "id:1,id:0" session results into per-topic before/after mastery.
    replay(results) {
      const course = M.course("python");
      const mastery = { ...s.student.mastery };
      const touched = {};
      results.forEach(({ id, correct }) => {
        const q = M.question(id);
        if (!(q.topic_id in touched)) touched[q.topic_id] = { before: mastery[q.topic_id] || 0, right: 0, total: 0 };
        mastery[q.topic_id] = M.student_extra.update(mastery[q.topic_id] || 0, correct);
        touched[q.topic_id].total++;
        if (correct) touched[q.topic_id].right++;
      });
      return Object.entries(touched).map(([tid, t]) => ({
        id: tid, name: course.taxonomy.find((x) => x.id === tid).name, ...t, after: mastery[tid],
      }));
    },
  };
})();
