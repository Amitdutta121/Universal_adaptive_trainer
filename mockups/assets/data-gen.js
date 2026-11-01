/*
 * Shared mock data for cross-subject generation and verification (Phase 3).
 * Load right after assets/data-g.js. It only ADDS to window.MOCK.
 *
 * The model: a question = stimulus + answer format + verifier. Each answer format declares
 * which verifier levels it can reach and which sandbox capabilities it needs. A subject
 * profile enables formats; a readiness gate (known-answer exercises + mutation tests) decides
 * which levels a subject has earned. A missing capability switches a format off (fails closed).
 * TODO(real): every number here is invented.
 */
(function () {
  const M = window.MOCK;

  // ---- Verification levels (strongest first) ------------------------------------------
  M.LEVELS = {
    proven: { label: "Computed", tone: "tone-ok", rank: 5, detail: "A program worked out the answer, and it matched the key." },
    crosschecked: { label: "Matched a reference", tone: "tone-ok", rank: 4, detail: "The key matched a reference table or database." },
    supported: { label: "Quoted", tone: "tone-accent", rank: 3, detail: "A sentence in your book states the answer, and independent AI solvers agree." },
    judged: { label: "AI-reviewed only", tone: "tone-muted", rank: 2, detail: "Only the AI reviewers looked at it. Read it closely." },
    rubric: { label: "Rubric-graded", tone: "tone-warn", rank: 1, detail: "Written answers graded against your rubric. Practice only." },
  };
  M.levelAtLeast = (a, b) => M.LEVELS[a].rank >= M.LEVELS[b].rank;

  // ---- Sandbox capabilities: probed at start-up, each with a known-answer program ----------
  M.capabilities = {
    checked: "2026-09-30 06:00",
    sandbox: "verifier-py312 · no network · 512 MB · 10 s per program",
    probes: [
      { id: "python", label: "Python 3.12 runner", probe: "print(7 // 2)", expect: "3", ok: true },
      { id: "numpy", label: "NumPy 2.1", probe: "np.mean([4, 8, 6, 2])", expect: "5.0", ok: true },
      { id: "scipy", label: "SciPy 1.14", probe: "norm.sf(2)", expect: "0.02275", ok: true },
      { id: "sympy", label: "SymPy 1.13", probe: "simplify(2*x - x - x)", expect: "0", ok: true },
      { id: "pint", label: "pint 0.24 (units)", probe: "Q_(1, 'm/s') + Q_(1, 'N')", expect: "DimensionalityError", ok: true },
      { id: "rdkit", label: "RDKit (molecules)", probe: "Descriptors.MolWt(MolFromSmiles('O'))", expect: "18.015", ok: false,
        error: "ModuleNotFoundError: No module named 'rdkit'" },
      { id: "biopython", label: "Biopython 1.84", probe: "Seq('TACGGA').complement().transcribe()", expect: "AUGCCU", ok: true },
      { id: "sqlite", label: "SQLite 3.46", probe: "select 2 + 2", expect: "4", ok: true },
      { id: "no_network", label: "Network blocked", probe: "urlopen('https://example.com')", expect: "blocked", ok: true },
      { id: "memory", label: "Memory limit enforced", probe: "bytearray(10**9)", expect: "MemoryError", ok: true },
    ],
  };
  M.capOk = (id) => M.capabilities.probes.find((p) => p.id === id)?.ok !== false;

  // ---- Answer formats: what each can prove, what it needs ---------------------------------
  M.FORMATS = {
    choice: { label: "Multiple choice", levels: ["proven", "supported", "judged"], needs: [] },
    true_false: { label: "True / false", levels: ["proven", "supported", "judged"], needs: [] },
    numeric: { label: "Numeric (tolerance, units)", levels: ["proven"], needs: ["numpy", "scipy", "pint"] },
    expression: { label: "Expression", levels: ["proven"], needs: ["sympy"] },
    ordering: { label: "Put in order", levels: ["crosschecked", "supported", "judged"], needs: [] },
    matching: { label: "Matching", levels: ["supported", "judged"], needs: [] },
    short_text: { label: "Short answer", levels: ["crosschecked", "supported"], needs: [] },
    explanation: { label: "Written explanation", levels: ["rubric"], needs: [] },
    balance: { label: "Balance the equation", levels: ["proven"], needs: ["rdkit"] },
    sequence: { label: "DNA / RNA sequence", levels: ["proven"], needs: ["biopython"] },
    code_output: { label: "Output prediction", levels: ["proven"], needs: ["python"] },
    code_write: { label: "Code completion, debugging, write a program", levels: ["proven"], needs: ["python"] },
    parsons: { label: "Order the lines of code", levels: ["proven"], needs: ["python"] },
  };
  M.formatAvailable = (f) => M.FORMATS[f].needs.every(M.capOk);

  // ---- Knowledge kinds found by section analysis -> formats that fit ------------------------
  M.KNOWLEDGE_KINDS = {
    fact: { label: "Fact or definition", formats: ["choice", "true_false", "short_text"] },
    quantitative: { label: "Quantitative relation", formats: ["numeric", "expression", "choice"] },
    procedure: { label: "Procedure or worked example", formats: ["numeric", "ordering", "code_write"] },
    sequence: { label: "Sequence or process", formats: ["ordering", "choice"] },
    classification: { label: "Classification", formats: ["matching", "choice"] },
    causal: { label: "Cause and effect", formats: ["choice", "explanation"] },
    code: { label: "Code behaviour", formats: ["code_output", "code_write", "parsons", "choice"] },
  };

  // ---- Subject profiles + readiness gates ---------------------------------------------------
  // gate: 30 published end-of-chapter exercises with answer keys per subject (OpenStax/OpenIntro),
  // plus mutation tests on approved questions. A level is earned when its bar is met.
  const P = (o) => o;
  M.profiles = [
    P({ id: "python", label: "Programming (Python)", wording: "introductory-Python", notation: "code",
        formats: [["code_output", "proven"], ["code_write", "proven"], ["parsons", "proven"], ["choice", "proven"], ["true_false", "proven"]],
        gate: { exercises: 30, programs: 0.97, quotes: 0.96, mutation_proven: 0.99, mutation_supported: 0.93 } }),
    P({ id: "statistics", label: "Statistics", wording: "introductory-statistics", notation: "LaTeX",
        formats: [["numeric", "proven"], ["expression", "proven"], ["choice", "proven"], ["true_false", "supported"], ["ordering", "supported"]],
        gate: { exercises: 30, programs: 0.96, quotes: 0.95, mutation_proven: 0.98, mutation_supported: 0.91 } }),
    P({ id: "physics", label: "Physics", wording: "introductory-physics", notation: "LaTeX",
        formats: [["numeric", "proven"], ["expression", "proven"], ["choice", "supported"], ["true_false", "supported"]],
        gate: { exercises: 30, programs: 0.96, quotes: 0.94, mutation_proven: 0.98, mutation_supported: 0.90 } }),
    P({ id: "chemistry", label: "Chemistry", wording: "general-chemistry", notation: "LaTeX",
        formats: [["numeric", "proven"], ["balance", "proven"], ["choice", "supported"], ["true_false", "supported"], ["matching", "supported"]],
        gate: { exercises: 30, programs: 0.95, quotes: 0.93, mutation_proven: 0.98, mutation_supported: 0.90 } }),
    P({ id: "biology", label: "Biology", wording: "introductory-biology", notation: "text",
        formats: [["choice", "supported"], ["true_false", "supported"], ["matching", "supported"], ["ordering", "supported"], ["numeric", "proven"], ["sequence", "proven"]],
        gate: { exercises: 30, programs: 0.96, quotes: 0.92, mutation_proven: 0.98, mutation_supported: 0.91 } }),
    P({ id: "history", label: "History", wording: "introductory U.S. history", notation: "text",
        formats: [["choice", "supported"], ["true_false", "supported"], ["ordering", "crosschecked"], ["matching", "supported"], ["short_text", "crosschecked"], ["explanation", "rubric"]],
        gate: { exercises: 30, programs: null, quotes: 0.88, mutation_proven: null, mutation_supported: 0.86 } }),
    P({ id: "general", label: "Other subject", wording: "introductory", notation: "text",
        formats: [["choice", "supported"], ["true_false", "supported"], ["short_text", "supported"]],
        gate: { exercises: 0, programs: null, quotes: null, mutation_proven: null, mutation_supported: null } }),
  ];
  M.BARS = { programs: 0.95, quotes: 0.9, mutation_proven: 0.98, mutation_supported: 0.9 };
  M.profile = (id) => M.profiles.find((p) => p.id === id) || M.profiles.at(-1);
  // Levels a subject has earned from its gate. Judged and rubric need no gate.
  M.earnedLevels = (p) => {
    const g = p.gate, B = M.BARS, out = ["judged", "rubric"];
    if (g.programs >= B.programs && g.mutation_proven >= B.mutation_proven) out.push("proven");
    if (g.quotes >= B.quotes && g.mutation_supported >= B.mutation_supported) out.push("supported", "crosschecked");
    return out;
  };
  // A profile format entry is [format, best]: best is the strongest level this subject's content
  // can reach with that format (a biology fact can be Supported, never Proven).
  // Returns the level it reaches today, or off with the reason (fails closed).
  M.formatStatus = (p, entry) => {
    const [f, best] = Array.isArray(entry) ? entry : [entry, M.FORMATS[entry].levels[0]];
    // Professor-facing reasons; the technical cause (which tool, which bar) is on the internal page.
    if (!M.formatAvailable(f)) return { f, best, on: false, tech: `Needs ${M.FORMATS[f].needs.filter((n) => !M.capOk(n)).join(", ")}, which failed its self-test`, why: "Temporarily unavailable: a checking tool is down" };
    const earned = M.earnedLevels(p);
    const level = M.FORMATS[f].levels.filter((l) => M.LEVELS[l].rank <= M.LEVELS[best].rank).find((l) => earned.includes(l));
    if (!level) return { f, best, on: false, tech: "Its checks haven't passed this subject's readiness bar yet", why: "Not available for this subject yet: its checks are still being validated" };
    return { f, best, on: true, level, capped: level !== best ? `Becomes ${M.LEVELS[best].label} once this subject's checks are validated` : "" };
  };
  // Keep MOCK.subjects (used by new-course and settings) in step with the profiles.
  M.subjects = M.profiles.map((p) => ({ id: p.id, label: p.label, types: M.subject(p.id)?.types || ["multiple_choice", "true_false"] }));
  M.subject = (id) => M.subjects.find((s) => s.id === id);

  // ---- Per-question verification (Python course mock questions) ------------------------------
  const CODEY = (q) => /`|\n/.test(q.prompt) || (q.options || []).some((o) => /[=<>()\[\]'"]/.test(o));
  // TODO(real): the quoted sentence comes from the stored section text; these stand in for it.
  const QUOTES = {
    "Return values": "If a function has no return statement, it returns None.",
    "with statements": "A with statement closes the file automatically when the block ends.",
    "Keys and values": "Keys must be hashable. A list can change, so it can't be used as a key.",
  };
  const MISCONCEPTIONS = {
    1000: ["Treats b = a as a copy", null, "Thinks b[0] = 42 replaces the whole list", "Expects assignment to a list item to fail"],
    1012: ["Thinks append on b leaves a alone", null, "Thinks append returns only the new item", "Expects append to fail on an alias"],
    1024: ["Thinks a slice is still an alias", null, "Confuses the slice with its first item", "Expects slicing to fail"],
    1036: ["Treats y = x as a copy", null, "Expects += to replace the list", "Confuses += with append of a list"],
    1006: ["Reads or as and", "Applies not to the wrong operand", null, "Assumes string comparison ignores case"],
    1009: ["Expects a default of 0", null, "Thinks a missing return is an error", "Thinks the last value is returned"],
  };
  M.verification = (q) => {
    if (!q) return null;
    const exec = M.question_types[q.type]?.code || CODEY(q);
    if (q.status === "validation_failed") return { level: "judged", failed: true, note: "The solution program disagreed with the key, so this never reached review." };
    if (exec) {
      const ans = q.options ? q.options[q.answer] : q.answer_text ?? String(q.answer);
      return { level: "proven", program: q.prompt.includes("\n") ? q.prompt.split("\n\n").slice(1).join("\n\n") || q.prompt : q.prompt.replace(/`/g, ""),
        output: ans, tests: M.question_types[q.type]?.code ? 4 : 0, misconceptions: MISCONCEPTIONS[q.id] || null };
    }
    const flagged = Object.values(q.judges).filter((v) => v === "flag").length;
    const solvers = flagged >= 2 ? 2 : 3;
    return {
      level: solvers === 3 ? "supported" : "judged",
      quotes: [{ text: QUOTES[q.subtopic] || "The section states the key directly.", section: q.source.section, found: true }],
      solvers: { agree: solvers, total: 3, models: "2 model families" },
      note: solvers < 3 ? "One solver picked a different answer, so it fell back to Judged. Read it closely." : "",
      misconceptions: MISCONCEPTIONS[q.id] || null,
    };
  };

  // ---- Section analysis: what's testable in a section (cached at import) ----------------------
  M.section_analysis = {
    "b1-9-5": { analysed: "2026-08-18", units: [
      { kind: "fact", text: "Two names can refer to the same list; a change through one is visible through the other (aliasing).", formats: ["choice", "true_false"], best: "proven" },
      { kind: "code", text: "b = a; b[0] = 42 changes what print(a) shows.", formats: ["code_output", "choice"], best: "proven" },
      { kind: "procedure", text: "Make an independent copy with the slice a[:].", formats: ["code_write", "choice"], best: "proven" },
    ], skipped: [{ text: "\"Aliasing is useful, but it can be surprising.\"", why: "An opinion, not something a question can check." }] },
    // OpenIntro Statistics, ch. 5 (illustrative): shows the same analysis on a non-code section.
    "b3-5-2": { book: "OpenIntro Statistics, 4th ed.", title: "5.2 Confidence intervals for a proportion", analysed: "2026-09-27", units: [
      { kind: "quantitative", text: "Margin of error = z* × √(p̂(1 − p̂)/n).", formats: ["numeric", "expression"], best: "proven" },
      { kind: "procedure", text: "Check conditions, compute p̂ and SE, find z*, build the interval.", formats: ["ordering", "numeric"], best: "proven" },
      { kind: "fact", text: "95% confidence describes the method's long-run capture rate, not one interval.", formats: ["choice", "true_false"], best: "supported" },
      { kind: "causal", text: "A larger sample gives a narrower interval.", formats: ["choice", "explanation"], best: "supported" },
    ], skipped: [{ text: "Figure 5.6 (simulated intervals)", why: "A figure; image questions aren't enabled." }] },
  };

  // ---- Assignment policy and verifier health ---------------------------------------------------
  M.assignment_min_level = { a1: "supported", a2: "supported", a3: "supported", a4: "supported", a5: "supported", a6: "proven" };
  M.verifier_health = {
    python: { mutants: 412, ran: "2026-09-29", rows: [
      { mutation: "Wrong key", proven: 0.995, supported: 0.94 },
      { mutation: "Number off by one", proven: 0.99, supported: null },
      { mutation: "Two options correct", proven: 0.97, supported: 0.9 },
      { mutation: "Quote not in the book", proven: null, supported: 1.0 },
      { mutation: "Answer leaked into the prompt", proven: 0.88, supported: 0.86 },
    ] },
  };
})();

// A Proven key means a solution program ran, so the deterministic "runs" check passed too
// (multiple choice and true/false questions about code included). Keeps question.html's checks
// table consistent with its "How the answer key was checked" card.
(function () {
  const M = window.MOCK;
  M.questions.forEach((q) => {
    if (q.checks.runs === "n/a" && M.verification(q)?.level === "proven") q.checks.runs = "pass";
  });
})();
