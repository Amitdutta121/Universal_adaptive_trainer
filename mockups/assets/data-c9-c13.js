/*
 * Extra mock data for pages C9–C13 (generate, questions, question, review, alignment).
 * Loaded right after mock-data.js. Only ADDS fields to window.MOCK.
 * TODO(real): every value in this file is invented.
 */
(function () {
  const M = window.MOCK;

  // TODO(real): per-call prices; the real app prices a sheet via /api/questions/batch-plan.
  M.pricing = { generation_call_usd: 0.011, judge_call_usd: 0.0035, judges_per_question: 4 };

  // TODO(real): the review queue is the 14 oldest questions that passed validation
  // (course.numbers.awaiting_review). mock-data.js marks more rows validation_passed
  // than that; the rest are treated as not yet queued.
  M.review_queue = M.questions
    .filter((q) => q.course === "python" && q.status === "validation_passed")
    .slice(0, M.course("python").numbers.awaiting_review)
    .map((q) => q.id);

  // TODO(real): mock-data.js points possible_duplicate_of at a question 11 ids earlier,
  // which has a different prompt (or does not exist). Re-point each flag at the nearest
  // question of the same type on the same subtopic (a variant of the same template, so the
  // prompts are near-identical) so the comparison makes sense.
  M.duplicates = (q) => {
    if (!q || !q.possible_duplicate_of.length) return [];
    const same = M.questions.filter((o) => o.id !== q.id && o.type === q.type && o.subtopic_id === q.subtopic_id);
    const near = same.sort((a, b) => Math.abs(a.id - q.id) - Math.abs(b.id - q.id))[0];
    return near ? [{ question_id: near.id, score: q.possible_duplicate_of[0].score }] : [];
  };

  // TODO(real): notes each judge wrote. Real rationales come from pedagogical_eval.metrics.
  const FLAG_NOTES = {
    issues: {
      multiple_choice: "Distractor 3 is implausible for this level; consider an off-by-one alternative.",
      true_false: "Correct as stated, but the statement does not say why. Students who guess right learn nothing; name the rule (keys must be hashable).",
      output_prediction: "end=' ' leaves a trailing space in the output; the expected answer should state whether it counts.",
      code_completion: "Fails for an empty string: word[0] raises IndexError. Either say the word is non-empty or accept word[:1].upper().",
      debugging: "Two fixes are valid (i += 1, or a for loop over range(5)); the answer key accepts only one.",
      parsons: "Line order is fine; the indentation of 'return total' is the only thing being tested at medium difficulty.",
      coding: "The empty-string test expects {} but the prompt does not mention empty input.",
    },
    subtopic: "Tests {other} more than {sub}; the concept named in the subtopic is incidental here.",
    difficulty: "Labelled {diff}, but it needs one step of reasoning; reads as {other_diff}.",
    generatability: "The cited section does not cover this directly.",
  };
  const PASS_NOTES = {
    issues: "No factual, answer or wording problems found.",
    subtopic: "Tests {sub} directly.",
    difficulty: "Matches {diff}: {diff_why}.",
    generatability: "Section {section} supports this question.",
  };
  const OTHER_SUB = { "range() and counted loops": "print formatting", "Slicing": "string methods", "while loops": "loop termination in general", "Logical operators": "comparison operators", "Keys and values": "hashability", "Counting with dicts": "string splitting", "Loop accumulators": "indentation", "Aliasing": "list mutation", "Scope": "function calls", "Return values": "function definitions", "with statements": "file modes" };
  M.judge_note = (q, judgeId) => {
    const verdict = q.judges[judgeId];
    const tpl = verdict === "flag"
      ? (judgeId === "issues" ? FLAG_NOTES.issues[q.type] : FLAG_NOTES[judgeId])
      : PASS_NOTES[judgeId];
    return tpl
      .replace("{sub}", q.subtopic.toLowerCase())
      .replace("{section}", q.source.section.split(" ")[0])
      .replace("{other}", OTHER_SUB[q.subtopic] || "a neighbouring subtopic")
      .replace("{diff}", q.difficulty)
      .replace("{diff_why}", { easy: "one concept, recall or one step", medium: "two concepts or one non-obvious step", hard: "several steps or a common misconception" }[q.difficulty])
      .replace("{other_diff}", q.difficulty === "easy" ? "medium" : "easy");
  };
  // TODO(real): issue codes attached to a flag.
  M.judge_codes = { issues: ["ambiguous_answer"], subtopic: ["off_subtopic"], difficulty: ["difficulty_mismatch"], generatability: ["not_in_source"] };

  // TODO(real): deterministic check details (real: validation_checks[].detail).
  M.check_detail = {
    schema: { pass: "All required fields present for this question type.", fail: "Missing field: options." },
    answer_consistency: { pass: "The answer key is consistent with the question body.", fail: "The keyed answer does not match the question body." },
    runs: { pass: "Reference solution ran in the sandbox; expected output matched.", fail: "Reference solution raised NameError on line 3.", "n/a": "Not a code question." },
  };

  // TODO(real): edit history beyond the "created" entry.
  M.question_history = (q) => {
    const h = q.history.slice();
    h.push({ at: `${q.created} 10:15`, who: "Checks", what: q.status === "validation_failed" ? "Failed deterministic checks" : "Passed deterministic checks" });
    h.push({ at: `${q.created} 10:16`, who: "Judges", what: `Panel r7: ${Object.values(q.judges).filter((v) => v === "flag").length} of 4 flagged` });
    if (q.status === "approved") h.push({ at: `${q.created} 16:40`, who: "Maya Chen", what: "Approved" });
    if (q.status === "rejected") h.push({ at: "2026-09-18 16:42", who: "Maya Chen", what: `Rejected: ${(M.rejection_reasons.find((r) => r[0] === q.rejection_reason) || ["", "Other"])[1]}` });
    return h;
  };

  // TODO(real): judge system prompts (real: GET /api/judge-prompts).
  M.judge_prompts = {
    issues: "You review one assessment question for an introductory course. Report every factual error, wrong answer key, ambiguous wording, or distractor that no student would pick. Quote the part of the question each issue is about. If there are none, say so; do not invent issues.",
    subtopic: "You are given a question and the subtopic it claims to test, with that subtopic's description. Decide whether answering the question requires the subtopic's concept. Incidental use of other concepts is fine; fail only when the claimed subtopic is not what the question tests.",
    difficulty: "Rate the question easy, medium or hard for a student who has just read the cited section. Easy: one concept, recall or one step. Medium: two concepts or one non-obvious step. Hard: several steps or a common misconception. Compare with the stated difficulty.",
    generatability: "You are given a textbook section and a question generated from it. Decide whether the section contains enough to answer the question. Fail when the question relies on material the section does not cover.",
  };

  // TODO(real): per-judge calibration detail (ADR-029/034) and week labels for trends.
  M.alignment.week_labels = ["Sep 2", "Sep 9", "Sep 16", "Sep 23", "Sep 30"];
  M.alignment.min_reviews = 20;
  M.alignment.rubric_version = "r7";
  M.alignment.disagreements = {
    issues: { flagged_you_approved: 11, passed_you_rejected: 8, new_since_learned: 4 },
    subtopic: { flagged_you_approved: 6, passed_you_rejected: 5, new_since_learned: 0 },
    difficulty: { flagged_you_approved: 27, passed_you_rejected: 12, new_since_learned: 7 },
    generatability: { flagged_you_approved: 2, passed_you_rejected: 4, new_since_learned: 0 },
  };
  M.alignment.duplicate_threshold = { value: 0.88, calibrated_on: 118, too_similar_rejections: 9 };
  // Which reject reasons each learned rule came from.
  M.alignment.rule_reasons = { r1: "Poor distractors", r2: "Poor wording", r3: "Too easy", r4: "Poor distractors" };
})();

/*
 * QView: renders a question's student-facing surface and its answer as HTML strings,
 * shared by question.html and review.html (x-html). Not data; kept here to avoid a
 * second shared file.
 */
(function () {
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const inline = (s) => esc(s).replace(/`([^`]+)`/g, '<code class="qv-code">$1</code>');
  const pre = (s, label) => `${label ? `<div class="qv-label">${label}</div>` : ""}<pre class="qv-pre">${esc(s).replace(/____/g, '<span class="qv-blank">____</span>')}</pre>`;
  const split = (prompt) => {
    const i = prompt.indexOf("\n\n");
    return i < 0 ? [prompt, null] : [prompt.slice(0, i), prompt.slice(i + 2)];
  };
  // Deterministic shuffle so a Parsons puzzle looks like what a student gets.
  const shuffle = (lines, seed) => {
    const out = lines.map((t, k) => ({ t, k }));
    let s = seed || 1;
    for (let i = out.length - 1; i > 0; i--) { s = (s * 16807) % 2147483647; const j = s % (i + 1); [out[i], out[j]] = [out[j], out[i]]; }
    return out;
  };
  const LETTERS = "ABCDEFGH";

  window.QView = {
    // Link params for section.html from a question's source citation.
    sourceParams(q) {
      const M = window.MOCK;
      const book = M.books.find((b) => b.title === q.source.book);
      if (!book) return null;
      for (const ch of M.books_sections[book.id] || [])
        for (const s of ch.sections) if (s.title === q.source.section) return { book: book.id, section: s.id };
      return { book: book.id };
    },
    student(q, prompt) {
      const [text, code] = split(prompt ?? q.prompt);
      let h = `<p class="qv-text">${inline(text)}</p>`;
      if (q.type === "multiple_choice") {
        h += `<ol class="qv-options">${q.options.map((o, k) => `<li><span class="qv-letter">${LETTERS[k]}</span><span>${inline(o)}</span></li>`).join("")}</ol>`;
      } else if (q.type === "true_false") {
        h += `<ol class="qv-options"><li><span class="qv-letter">T</span>True</li><li><span class="qv-letter">F</span>False</li></ol>`;
      } else if (q.type === "output_prediction") {
        h += pre(code) + `<div class="qv-input">Student types the printed output</div>`;
      } else if (q.type === "code_completion") {
        h += pre(code) + `<div class="qv-input">Student fills the blank</div>`;
      } else if (q.type === "debugging") {
        h += pre(code, "Broken code") + `<div class="qv-input">Student edits the code and runs it</div>`;
      } else if (q.type === "parsons") {
        h += `<div class="qv-label">Blocks, as shuffled for the student</div><ol class="qv-blocks">${shuffle(q.lines, q.id).map((l) => `<li><i data-lucide="grip-vertical"></i><code>${esc(l.t.trim())}</code></li>`).join("")}</ol>`;
      } else if (q.type === "coding") {
        h += `<div class="qv-input qv-editor">def count_words(text):<br>&nbsp;&nbsp;&nbsp;&nbsp;# student's code, run against hidden tests</div>`;
      }
      return h;
    },
    answer(q) {
      if (q.type === "multiple_choice") return `<p><span class="qv-letter qv-ok">${LETTERS[q.answer]}</span> ${inline(q.options[q.answer])}</p>`;
      if (q.type === "true_false") return `<p><span class="pill tone-ok">${q.answer ? "True" : "False"}</span></p>`;
      if (q.type === "parsons") return pre(q.lines.join("\n"), "Assembled in canonical order");
      if (q.type === "output_prediction") return pre(q.answer_text, "Expected output");
      if (q.type === "coding") return `<p class="qv-text">${inline(q.answer_text)}</p>`;
      if (q.type === "code_completion") return pre(q.answer_text, "Accepted answer");
      return `<p class="qv-text">${inline(q.answer_text)}</p>`;
    },
  };
})();
