/*
 * Extra mock data for the group D (teach) pages: question sets, classes, students, student.
 * Load right after assets/mock-data.js. It only ADDS fields to window.MOCK.
 * TODO(real): every value in this file is invented.
 */
(function () {
  const M = window.MOCK;
  let seed = 41;
  const rand = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;

  // TODO(real): frozen question_count vs live member_count (ADR-036). qs1 lost one row to a
  // deleted question, so it reads 13 / 14.
  const approvedIds = M.questions.filter((q) => q.status === "approved").map((q) => q.id);
  const editedSince = [1003, 1011, 1019]; // were approved when qs2 froze, edited back into review since
  M.question_set_members = {
    qs2: [...approvedIds, ...editedSince].sort((a, b) => a - b),
    qs1: approvedIds.slice(0, 13),
  };
  M.question_set_edited_since = { qs2: editedSince };
  M.question_set_frozen_count = { qs2: 23, qs1: 14 };
  M.question_set_frozen_by = { qs2: "Maya Chen", qs1: "Maya Chen" };

  // TODO(real): what "Freeze a new set" would include if pressed now.
  M.freeze_preview = {
    python: { approved: 23, coverage_pct: window.MOCK.courses[0].numbers.coverage_pct, added_since_last: 3, edited_since_last: 3 },
    statistics: { approved: 0, coverage_pct: 0, added_since_last: 0, edited_since_last: 0 },
  };

  // TODO(real): allowed-emails list for classes with roster restriction on.
  const c2emails = M.students.filter((s) => s.class_id === "c2").map((s) => s.email);
  M.class_allowed_emails = {
    c1: [],
    c2: [...c2emails, "hana.yilmaz@example.edu", "omar.said@example.edu", "lucia.romano@example.edu"],
  };
  M.join_base = "trainer.example.edu/join"; // TODO(real): hosted domain

  // TODO(real): attempts and sessions per student, generated deterministically from the
  // student's mastery so a weak topic shows mostly low scores.
  const topicByName = {};
  M.course("python").taxonomy.forEach((t) => { topicByName[t.name] = t; });
  const members = M.question_set_members.qs2.map((id) => M.question(id));
  const cache = {};
  M.attemptsFor = function (studentId) {
    if (cache[studentId]) return cache[studentId];
    const s = M.student(studentId);
    if (!s) return { attempts: [], sessions: [] };
    seed = 1000 + Number(studentId.slice(1)) * 97;
    const lastDay = Number(s.last_active.slice(8));
    const sessions = [];
    for (let k = 0; k < s.sessions; k++) {
      const day = Math.max(6, lastDay - (s.sessions - 1 - k) * 2);
      const served = 4 + Math.floor(rand() * 10);
      const open = k === s.sessions - 1 && lastDay >= 27;
      sessions.push({
        id: 300 + Number(studentId.slice(1)) * 20 + k,
        set: "Midterm practice", started: `2026-09-${String(day).padStart(2, "0")} ${String(9 + Math.floor(rand() * 10)).padStart(2, "0")}:${String(Math.floor(rand() * 60)).padStart(2, "0")}`,
        served, answered: open ? served - 1 : served, status: open ? "open" : "closed",
      });
    }
    const attempts = [];
    const n = Math.min(14, s.attempts);
    // Only topics the student has practised (mastery 0 = not measured yet).
    const pool = members.filter((q) => s.mastery[topicByName[q.topic].id] > 0);
    for (let k = 0; k < n; k++) {
      const q = pool[Math.floor(rand() * pool.length)];
      const topic = topicByName[q.topic];
      const m = s.mastery[topic.id] || 0.3;
      const partial = ["coding", "debugging", "code_completion", "parsons"].includes(q.type);
      const ok = rand() < m;
      const score = partial ? (ok ? 100 : 20 * Math.floor(rand() * 4)) : ok ? 100 : 0;
      const day = Math.max(6, lastDay - Math.floor(k / 4));
      attempts.push({
        id: 9000 + k, question_id: q.id, prompt: q.prompt, type: q.type, topic: q.topic, subtopic: q.subtopic,
        difficulty: q.difficulty, score,
        at: `2026-09-${String(day).padStart(2, "0")} ${String(20 - (k % 4) * 2).padStart(2, "0")}:${String(10 + k * 3).padStart(2, "0")}`,
      });
    }
    // Per-subtopic weakness for the weak list (ADR-041: floored at 0.05, starts at 1.0).
    const weak = s.weak_subtopics.map((name, i) => ({ name, weakness: Math.round((0.78 - i * 0.12) * 100) / 100 }));
    const res = { attempts, sessions, weak };
    cache[studentId] = res;
    return res;
  };

  // TODO(real): observations (scored attempts) per topic for the detail page.
  M.topicObservations = function (student, topicId) {
    const m = student.mastery[topicId];
    if (!m) return 0;
    return 2 + Math.round((m * 7 + Number(topicId.split("t")[1])) % 9);
  };
})();
