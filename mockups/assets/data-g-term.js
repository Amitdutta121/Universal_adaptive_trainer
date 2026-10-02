/*
 * Page-only mock data for G10 (term report), G11 (weekly digest), G0 (sample course state)
 * and the E1 Settings roles change. Load after assets/data-g.js. Only ADDS to window.MOCK.
 * TODO(real): every value in this file is invented.
 */
(function () {
  const M = window.MOCK;

  // ---- E1 course roles (replaces the two-role list in data-b.js on the settings page) ----
  // TODO(real): enforced server-side per course membership.
  M.course_roles = [
    { id: "co_instructor", label: "Co-instructor", detail: "Everything the owner can do except deleting the course." },
    { id: "ta", label: "TA", detail: "Reviews questions, sees students and the gradebook, handles student reports. No settings, no deleting, no exports of student data." },
    { id: "grader", label: "Grader", detail: "Gradebook only: scores and extensions." },
  ];
  // Rows of the permission matrix. Order of flags: owner, co_instructor, ta, grader.
  M.role_permissions = [
    ["Materials and taxonomy", "View", [1, 1, 1, 0]],
    ["Materials and taxonomy", "Upload books, edit the taxonomy", [1, 1, 0, 0]],
    ["Questions", "Generate questions (uses the AI budget)", [1, 1, 0, 0]],
    ["Questions", "Review, edit, approve and reject", [1, 1, 1, 0]],
    ["Questions", "Import questions, export an exam", [1, 1, 0, 0]],
    ["Teaching", "Schedule, assignments, question sets, classes", [1, 1, 0, 0]],
    ["Teaching", "Handle student reports (reply, edit, void)", [1, 1, 1, 0]],
    ["Students", "See students, mastery and insights", [1, 1, 1, 0]],
    ["Students", "Gradebook: scores and extensions", [1, 1, 1, 1]],
    ["Students", "Export student data (CSV, send to Canvas)", [1, 1, 0, 0]],
    ["Course", "Settings, LMS connection, collaborators", [1, 1, 0, 0]],
    ["Course", "Copy to a new term, archive", [1, 1, 0, 0]],
    ["Course", "Delete the course", [1, 0, 0, 0]],
  ];
  // Extra people on a course beyond MOCK.users. TODO(real): pending invitation record.
  M.term_collaborators = [
    { course: "python", id: "u3", name: "Priya Natarajan", email: "p.natarajan@example.edu", initials: "PN", role: "ta", pending: true, invited: "2026-09-29" },
  ];

  // ---- G10 term report -------------------------------------------------------------------
  // TODO(real): enrolment history from the roster / LMS.
  M.term_report = {
    python: {
      as_of: "2026-09-30", week: 5, weeks: 15,
      final_after: "2026-12-16", // report is regenerated after the final exam
      enrolment: { first_day: 28, added: 1, dropped: 1, drop_deadline: "2026-09-11", now: 28,
        dropped_note: "1 student dropped before the Sep 11 deadline; 1 added on Sep 15 (Quinn Murphy)." },
      reports_median_hours: 8.2, // median time from report to resolution
      generated: 60, rejected_reasons: [["Incorrect answer", 3], ["Too similar to another question", 2], ["Poor wording", 2]],
    },
  };

  // ---- G11 weekly digest -------------------------------------------------------------------
  // TODO(real): digest subscription stored per user.
  M.digest = {
    send_day: "Monday", send_time: "07:00", next_send: "Mon, Oct 5, 7:00 AM", courses: ["python", "biology", "statistics"],
    from: "Adaptive Trainer <digest@trainer.example.edu>",
    last_sent: "Mon, Sep 28, 7:00 AM",
  };
})();
