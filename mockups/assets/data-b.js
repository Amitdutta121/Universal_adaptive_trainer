/*
 * Extra mock data for groups B (workspace) and E (course settings). Loaded right after
 * mock-data.js; only ADDS fields to window.MOCK.
 * TODO(real): every value below is invented.
 */
(function () {
  const M = window.MOCK;

  // TODO(real): recent activity across the professor's courses (would come from an audit/event log).
  M.activity = [
    { when: "12 min ago", course: "python", who: "Daniel Ortiz", text: "approved 4 questions in Loops and Lists", file: "review.html" },
    { when: "2 h ago", course: "statistics", who: "Maya Chen", text: "uploaded OpenIntro Statistics (64 sections)", file: "materials.html" },
    { when: "Sep 28", course: "statistics", who: "AI draft", text: "proposed a taxonomy: 8 topics, 29 subtopics", file: "taxonomy-draft.html" },
    { when: "Sep 27", course: "python", who: "Judges", text: "re-run stopped after 17 of 42 questions (rate limit)", file: "jobs.html" },
    { when: "Sep 26", course: "python", who: "Aisha Okafor", text: "and 5 other students joined Section 002", file: "classes.html" },
    { when: "Sep 20", course: "python", who: "Maya Chen", text: "froze question set “Midterm practice” (23 questions)", file: "question-sets.html" },
  ];

  // TODO(real): per-course book / taxonomy-version counts, mirroring /api/counts on the current dashboard.
  M.course_counts = {
    python: { books: 2, taxonomy_versions: 3, learned_rules: 4 },
    statistics: { books: 1, taxonomy_versions: 1, learned_rules: 0 },
  };

  // TODO(real): collaborator roles offered when inviting (F2).
  M.roles = [
    { id: "co_instructor", label: "Co-instructor", detail: "Everything the owner can do except deleting the course." },
    { id: "ta", label: "TA", detail: "Reviews questions, sees students and the gradebook, handles student reports. No settings or student-data exports." },
    { id: "grader", label: "Grader", detail: "Gradebook only: scores and extensions." },
  ]; // same three roles as MOCK.course_roles (data-g-term.js) on the Settings page

  // TODO(real): email notification preferences for the signed-in professor.
  M.notification_prefs = [
    { id: "job_failed", label: "A background job fails", detail: "With the error and a link to retry.", on: true },
    { id: "job_done", label: "A long job finishes", detail: "Generation, book import, taxonomy draft.", on: true },
    { id: "review_digest", label: "Weekly digest", detail: "Monday 7:00: what each class got wrong, who hasn't started, reports and questions waiting.", on: true },
    { id: "usage_warn", label: "Usage reaches the warning level", detail: "Sent once per month when spend passes the warning threshold.", on: true },
    { id: "student_join", label: "Students join a class", detail: "One email per day at most.", on: false },
  ];

  // TODO(real): LTI 1.3 tool endpoints this deployment would publish (F11).
  M.lti_tool = {
    login_url: "https://trainer.example.edu/lti/login",
    redirect_uri: "https://trainer.example.edu/lti/launch",
    jwks_url: "https://trainer.example.edu/lti/jwks.json",
    target_link_uri: "https://trainer.example.edu/lti/course/",
  };

  // TODO(real): the account's institution and time zone.
  M.me_profile = { institution: "Example State University", department: "Computer Science & Engineering", timezone: "America/Los_Angeles (Pacific)" };
})();
