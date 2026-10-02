/*
 * Page-only helpers for G1 schedule, G2 assignments, G3 assignment editor and the F2s due line.
 * Load after assets/data-g.js. Only ADDS to window.MOCK (under MOCK.plan).
 */
(function () {
  const M = window.MOCK;
  const DAY = 86400000;
  const d = (s) => new Date(s + "T12:00:00");

  M.plan = {
    // Week number (1–15) a date falls in, or null outside the term.
    weekOf(courseId, date) {
      const s = M.schedule[courseId];
      if (!s) return null;
      const w = Math.floor((d(date) - d(s.term.starts)) / (7 * DAY)) + 1;
      return w >= 1 && w <= s.weeks.length ? w : null;
    },
    // { topicId: week } for every scheduled topic.
    topicWeeks(courseId) {
      const out = {};
      (M.schedule[courseId]?.weeks || []).forEach((w) => w.topics.forEach((t) => { out[t] = w.week; }));
      return out;
    },
    // Median of a list of numbers (null for an empty list).
    median(xs) {
      if (!xs.length) return null;
      const s = [...xs].sort((a, b) => a - b);
      const m = Math.floor(s.length / 2);
      return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
    },
    // TODO(real): the server would simulate the selector + BKT update from the student's state.
    // Stand-in: about one question per 3.5 mastery points still missing, plus 4 to confirm the
    // estimate, and 0 once the student is already at the target.
    questionsToGoal(mastery, target) {
      if (mastery >= target) return 0;
      return Math.ceil((target - mastery) / 0.035) + 4;
    },
    // TODO(real): median time per answer from attempt logs. Invented: 1.3 min per question.
    minutesPerQuestion: 1.3,
    // TODO(real): median answers per session from session logs. Invented.
    questionsPerSession: 14,
    // Canvas column names for the LMS field. TODO(real): read from the LTI line items.
    lms: { platform: "Canvas", connected: true },
  };
})();
