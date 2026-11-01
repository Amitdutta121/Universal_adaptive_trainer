/*
 * A third course, in a third subject, so the workspace shows a professor running several courses:
 *   CS 135 Intro to Python  (running, week 5)  · BIOL 190 Intro Biology (running, week 5, 3 sections)
 *   STAT 152 Intro Statistics (being set up)
 * Biology has its own students, question bank, coverage, schedule, assignments with per-student
 * results, insights and reports, all derived here so its pages agree with each other.
 * Also MOCK.course_week: a one-line "this week" summary per running course for My courses.
 * Load last, right before assets/layout.js. It only ADDS to window.MOCK.
 * TODO(real): every Biology value is invented. Question text is real intro-biology content.
 */
(function () {
  const M = window.MOCK;
  if (M.courses.some((c) => c.id === "biology")) return; // loaded twice

  let seed = 19;
  const rand = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;
  const pick = (a) => a[Math.floor(rand() * a.length)];
  const r2 = (x) => Math.round(x * 100) / 100;
  const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);

  // ---- Taxonomy ---------------------------------------------------------------------------
  let sid = 9000;
  const topics = [
    ["Chemistry of life", ["Water and pH", "Macromolecules", "Enzymes"]],
    ["Cells", ["Prokaryotes and eukaryotes", "Organelles", "Membranes and transport"]],
    ["Energy in cells", ["ATP", "Glycolysis", "Cellular respiration", "Photosynthesis"]],
    ["Cell division", ["Mitosis", "Meiosis", "Cell cycle control"]],
    ["Genetics", ["Mendelian inheritance", "Punnett squares", "Linked genes"]],
    ["Molecular biology", ["DNA replication", "Transcription", "Translation"]],
  ].map(([name, subs], i) => ({
    id: `bio-t${i + 1}`, name,
    subtopics: subs.map((s) => ({ id: sid++, name: s, description: `What a student should be able to do with ${s.toLowerCase()}.` })),
  }));
  const subByName = {};
  topics.forEach((t) => t.subtopics.forEach((s) => { subByName[s.name] = { t, s }; }));

  // ---- Book -------------------------------------------------------------------------------
  M.books.push({ id: "b4", course: "biology", title: "OpenStax Biology 2e", authors: "Clark, Douglas, Choi", format: "book_pdf", status: "imported",
    chapters: 47, sections: 312, embedded: 312, structure_source: "pdf_outline", confidence: "high", uploaded: "2026-08-22", warnings: [] });
  const SECTION = {
    "Chemistry of life": "2.2 Water", "Cells": "4.3 Eukaryotic cells", "Energy in cells": "7.2 Glycolysis",
    "Cell division": "10.2 The cell cycle", "Genetics": "12.2 Characteristics and traits", "Molecular biology": "15.2 Prokaryotic transcription",
  };

  // ---- Questions --------------------------------------------------------------------------
  // [subtopic, type, difficulty, status, prompt, options|answer, key index, extras]
  // status: A approved · P awaiting review · F failed checks · R rejected · G generated (not yet checked)
  const ST = { A: "approved", P: "validation_passed", F: "validation_failed", R: "rejected", G: "generated" };
  const Q = [
    ["Water and pH", "multiple_choice", "medium", "A", "A solution at pH 3 has how many times more H⁺ ions than a solution at pH 5?", ["2", "10", "100", "1,000"], 2,
      { program: "10 ** (5 - 3)  # -> 100", wrong: ["Subtracts the pH values", "Treats one pH step as ×5", null, "Counts three steps instead of two"] }],
    ["Water and pH", "true_false", "easy", "A", "Water's high specific heat comes mainly from hydrogen bonds between its molecules.", true, null,
      { quote: "Hydrogen bonds must be broken before water molecules can move faster, which gives water a high specific heat." }],
    ["Macromolecules", "multiple_choice", "easy", "A", "Which macromolecule is built from nucleotides?", ["Proteins", "Lipids", "Nucleic acids", "Carbohydrates"], 2,
      { quote: "Nucleic acids are polymers of nucleotides." }],
    ["Macromolecules", "multiple_choice", "easy", "A", "Which bond joins amino acids in a protein?", ["Glycosidic bond", "Peptide bond", "Ester bond", "Phosphodiester bond"], 1,
      { quote: "Amino acids are joined by peptide bonds." }],
    ["Macromolecules", "true_false", "medium", "A", "Saturated fatty acids contain at least one carbon–carbon double bond.", false, null,
      { quote: "Saturated fatty acids have only single bonds between neighbouring carbons." }],
    ["Enzymes", "multiple_choice", "medium", "A", "Far above an enzyme's optimum temperature, the reaction usually slows because the enzyme…",
      ["runs out of substrate", "denatures and its active site loses its shape", "becomes a competitive inhibitor", "lowers the activation energy further"], 1,
      { quote: "High temperatures can denature an enzyme, changing the shape of its active site.", wrong: ["Confuses rate with supply", null, "Mixes up inhibition and denaturation", "Thinks heat always speeds reactions"] }],
    ["Enzymes", "multiple_choice", "medium", "A", "A competitive inhibitor…",
      ["binds the active site and competes with the substrate", "binds elsewhere and changes the enzyme's shape", "raises the activation energy", "is used up by the reaction"], 0,
      { quote: "A competitive inhibitor competes with the substrate for the active site." }],
    ["Enzymes", "true_false", "hard", "A", "Enzymes lower a reaction's activation energy but do not change its ΔG.", true, null,
      { quote: "Enzymes lower the activation energy; they do not change whether a reaction is exergonic or endergonic." }],
    ["Enzymes", "multiple_choice", "hard", "R", "Which of these is not a protein?", ["Amylase", "Hemoglobin", "Ribozyme", "Insulin"], 2, { reason: "ambiguous" }],

    ["Prokaryotes and eukaryotes", "multiple_choice", "easy", "A", "Which structure do both prokaryotic and eukaryotic cells have?", ["Nucleus", "Mitochondria", "Ribosomes", "Endoplasmic reticulum"], 2,
      { quote: "All cells have ribosomes." }],
    ["Prokaryotes and eukaryotes", "true_false", "easy", "A", "Prokaryotic cells have a membrane-bound nucleus.", false, null,
      { quote: "Prokaryotes lack a membrane-bound nucleus." }],
    ["Organelles", "multiple_choice", "easy", "A", "In a eukaryotic cell, where is most ATP made?", ["Nucleus", "Ribosome", "Mitochondrion", "Golgi apparatus"], 2,
      { quote: "Mitochondria are the sites of cellular respiration, where most ATP is made." }],
    ["Organelles", "multiple_choice", "medium", "A", "A cell that secretes a lot of protein would have an unusually large amount of…", ["smooth ER", "rough ER", "lysosomes", "peroxisomes"], 1,
      { quote: "The rough ER makes proteins destined for secretion.", wrong: ["Confuses smooth and rough ER", null, "Thinks lysosomes package proteins", "Picks an unrelated organelle"] }],
    ["Organelles", "multiple_choice", "easy", "A", "Which organelle modifies and packages proteins for secretion?", ["Golgi apparatus", "Lysosome", "Nucleolus", "Vacuole"], 0,
      { quote: "The Golgi apparatus sorts, tags and packages proteins." }],
    ["Membranes and transport", "multiple_choice", "medium", "A", "A red blood cell is placed in a hypertonic solution. What happens?",
      ["It swells and may burst", "It shrinks as water leaves", "Nothing; water moves equally both ways", "It pumps salt in to match"], 1,
      { quote: "In a hypertonic solution, water leaves the cell and the cell shrinks.", wrong: ["Reverses hypertonic and hypotonic", null, "Thinks equilibrium means no change", "Thinks cells actively balance osmosis"] }],
    ["Membranes and transport", "multiple_choice", "medium", "A", "What moves glucose into a cell against its concentration gradient?", ["Simple diffusion", "Facilitated diffusion", "Active transport", "Osmosis"], 2,
      { quote: "Moving a substance against its concentration gradient requires active transport." }],
    ["Membranes and transport", "true_false", "easy", "A", "Small nonpolar molecules like O₂ cross the lipid bilayer by simple diffusion.", true, null,
      { quote: "Oxygen and carbon dioxide diffuse directly through the membrane." }],
    ["Membranes and transport", "multiple_choice", "hard", "F", "Inside a cell the solute concentration is 0.3 M; outside it is 0.5 M. Which way does water move?",
      ["Into the cell", "Out of the cell", "No net movement", "It depends only on temperature"], 1, { fail: "The answer key disagreed with the solution program on one variant." }],

    ["ATP", "multiple_choice", "easy", "A", "Energy is released from ATP when…", ["a phosphate bond is hydrolysed", "ATP binds oxygen", "adenine is oxidized", "ATP enters the nucleus"], 0,
      { quote: "Hydrolysis of ATP's terminal phosphate bond releases energy." }],
    ["ATP", "true_false", "medium", "A", "ATP is the cell's long-term energy store.", false, null,
      { quote: "ATP is used immediately; cells store energy long-term as fat and glycogen." }],
    ["Glycolysis", "multiple_choice", "easy", "A", "Where does glycolysis take place?", ["Mitochondrial matrix", "Cytoplasm", "Inner mitochondrial membrane", "Nucleus"], 1,
      { quote: "Glycolysis takes place in the cytoplasm." }],
    ["Glycolysis", "true_false", "medium", "A", "Glycolysis requires oxygen.", false, null,
      { quote: "Glycolysis does not use oxygen; it occurs in both aerobic and anaerobic conditions." }],
    ["Glycolysis", "multiple_choice", "medium", "A", "What is the net ATP yield of glycolysis per glucose?", ["1", "2", "4", "36"], 1,
      { program: "made, used = 4, 2\nprint(made - used)  # -> 2", wrong: ["Halves the net yield", null, "Forgets the 2 ATP invested", "Gives the whole of respiration"] }],
    ["Glycolysis", "multiple_choice", "easy", "A", "The end product of glycolysis is…", ["Acetyl-CoA", "Pyruvate", "Always lactate", "Citrate"], 1,
      { quote: "Glycolysis ends with two molecules of pyruvate." }],
    ["Cellular respiration", "multiple_choice", "medium", "A", "Which stage of cellular respiration makes the most ATP?", ["Glycolysis", "Pyruvate oxidation", "Citric acid cycle", "Oxidative phosphorylation"], 3,
      { quote: "Most ATP is made by oxidative phosphorylation." }],
    ["Cellular respiration", "multiple_choice", "medium", "A", "What is the final electron acceptor in the electron transport chain?", ["NAD⁺", "Oxygen", "Water", "Carbon dioxide"], 1,
      { quote: "Oxygen is the final electron acceptor; it is reduced to water.", wrong: ["Confuses carriers with the final acceptor", null, "Names the product, not the acceptor", "Thinks CO₂ takes the electrons"] }],
    ["Cellular respiration", "multiple_choice", "hard", "P", "Cyanide blocks the electron transport chain. What happens to ATP made by oxidative phosphorylation?",
      ["It increases to compensate", "It stops", "It is unaffected because glycolysis continues", "Only the citric acid cycle stops"], 1,
      { quote: "Without electron flow, no proton gradient forms and ATP synthase stops." }],
    ["Cellular respiration", "true_false", "hard", "P", "The carbon atoms in the CO₂ you breathe out come from glucose.", true, null,
      { quote: "The carbons of glucose leave as CO₂ during pyruvate oxidation and the citric acid cycle." }],
    ["Photosynthesis", "multiple_choice", "medium", "A", "Where do the light-dependent reactions happen?", ["Stroma", "Thylakoid membranes", "Cytoplasm", "Mitochondria"], 1,
      { quote: "The light-dependent reactions take place in the thylakoid membranes." }],
    ["Photosynthesis", "true_false", "hard", "A", "The O₂ released in photosynthesis comes from CO₂.", false, null,
      { quote: "The oxygen released comes from splitting water." }],
    ["Photosynthesis", "multiple_choice", "medium", "P", "Which molecule does the Calvin cycle produce?", ["O₂", "G3P, a three-carbon sugar", "ATP", "Water"], 1,
      { quote: "The Calvin cycle produces G3P." }],

    ["Mitosis", "multiple_choice", "easy", "P", "In which phase do sister chromatids separate?", ["Prophase", "Metaphase", "Anaphase", "Telophase"], 2,
      { quote: "In anaphase the sister chromatids separate." }],
    ["Mitosis", "true_false", "easy", "P", "Mitosis produces two genetically identical daughter cells.", true, null,
      { quote: "Mitosis results in two identical daughter nuclei." }],
    ["Meiosis", "multiple_choice", "medium", "P", "A cell with 2n = 46 goes through meiosis. How many chromosomes are in each resulting cell?", ["46", "23", "92", "12"], 1,
      { program: "2 * 23 // 2  # n = 23", wrong: ["Confuses meiosis with mitosis", null, "Doubles instead of halving", "Halves twice"] }],
    ["Meiosis", "multiple_choice", "medium", "P", "Crossing over happens during…", ["Prophase I", "Metaphase II", "Anaphase I", "Telophase II"], 0,
      { quote: "Crossing over occurs in prophase I." }],
    ["Cell cycle control", "true_false", "medium", "G", "Cancer can result from mutations that disable cell-cycle checkpoints.", true, null, {}],
    ["Cell cycle control", "multiple_choice", "hard", "G", "A drug blocks spindle formation. Dividing cells would stop in…", ["G1", "S phase", "M phase, at metaphase", "G2"], 2, {}],

    ["Mendelian inheritance", "multiple_choice", "easy", "A", "In peas, purple (P) is dominant to white (p). What color is a Pp plant?", ["White", "Purple", "Lavender", "Half purple, half white"], 1,
      { quote: "A heterozygote shows the dominant trait." }],
    ["Punnett squares", "multiple_choice", "medium", "A", "Two Aa plants are crossed. What fraction of the offspring are aa?", ["1/2", "1/4", "3/4", "0"], 1,
      { program: "from itertools import product\nkids = [a + b for a, b in product('Aa', 'Aa')]\nprint(kids.count('aa'), '/', len(kids))  # -> 1 / 4" }],
    ["Punnett squares", "multiple_choice", "hard", "A", "AaBb × AaBb, with unlinked genes. What fraction show both dominant traits?", ["3/4", "9/16", "1/4", "3/16"], 1,
      { program: "# enumerate the 16 gamete pairs\n# count A_B_ -> 9 of 16", wrong: ["Counts one gene only", null, "Counts a single-dominant class", "Counts one mixed class"] }],
    ["Punnett squares", "multiple_choice", "hard", "A", "A carrier mother (XᴬXᵃ) and an unaffected father have a son. What is the chance he is affected by the X-linked recessive trait?", ["0", "1/4", "1/2", "1"], 2,
      { program: "# son gets the father's Y; his X comes from the mother: Xᴬ or Xᵃ\n# P(Xᵃ) = 1/2", wrong: ["Thinks sons can't be affected", "Uses the chance for any child", null, "Assumes every son is affected"] }],
    ["Linked genes", "true_false", "medium", "P", "Genes close together on the same chromosome tend to be inherited together.", true, null,
      { quote: "Linked genes close together are rarely separated by crossing over." }],

    ["DNA replication", "multiple_choice", "medium", "P", "DNA polymerase adds nucleotides to which end of a growing strand?", ["The 5′ end", "The 3′ end", "Either end", "The middle"], 1,
      { quote: "DNA polymerase adds nucleotides only to the 3′ end." }],
    ["Transcription", "multiple_choice", "hard", "G", "A DNA template strand reads 3′-TAC GGA-5′. What is the mRNA?", ["5′-AUG CCU-3′", "5′-ATG CCT-3′", "5′-UAC GGA-3′", "3′-AUG CCU-5′"], 0,
      { program: "Seq('TACGGA').complement().transcribe()  # -> AUGCCU" }],
    ["Translation", "true_false", "easy", "G", "Each codon is three nucleotides long.", true, null, {}],
    ["Translation", "multiple_choice", "easy", "R", "Which molecule carries amino acids to the ribosome?", ["mRNA", "tRNA", "rRNA", "DNA"], 1, { reason: "too_similar_repetitive" }],
  ];

  const bioQuestions = Q.map(([sub, type, diff, st, prompt, opts, key, x], i) => {
    const { t, s } = subByName[sub];
    const status = ST[st];
    const created = i < 30 ? `2026-08-${String(22 + (i % 9)).padStart(2, "0")}` : `2026-09-${String(2 + ((i - 30) % 26)).padStart(2, "0")}`;
    const flagged = st === "R" || i % 11 === 5 ? 2 : i % 7 === 3 ? 1 : 0;
    const judges = { issues: "pass", subtopic: "pass", difficulty: "pass", generatability: "pass" };
    if (flagged >= 1) judges.difficulty = "flag";
    if (flagged >= 2) judges.issues = "flag";
    return {
      id: 2000 + i, course: "biology", type, prompt,
      options: type === "multiple_choice" ? opts : null, answer: type === "multiple_choice" ? key : opts,
      answer_text: null, lines: null,
      topic_id: t.id, topic: t.name, subtopic_id: s.id, subtopic: s.name, difficulty: diff, status,
      source: { book: "OpenStax Biology 2e", section: SECTION[t.name] },
      checks: { schema: "pass", answer_consistency: st === "F" ? "fail" : "pass", runs: x.program ? "pass" : st === "F" ? "fail" : "n/a" },
      judges, judge_notes: x.fail || "The distractors match common errors for this level.",
      possible_duplicate_of: [], rejection_reason: st === "R" ? x.reason : null,
      created, generator: `run-${12 + Math.floor(i / 8)}`,
      history: [{ at: `${created} 09:30`, who: "Generator", what: `Created from section ${SECTION[t.name].split(" ")[0]}` }],
      solution_program: x.program || null, quote: x.quote || null, wrong: x.wrong || null,
    };
  });
  M.questions.push(...bioQuestions);

  // How a Biology answer key was checked: a program where there is one, else the quoted sentence
  // plus blind solvers; two judge flags drop it to AI-reviewed only.
  const baseVerification = M.verification;
  M.verification = (q) => {
    if (!q || q.course !== "biology") return baseVerification(q);
    if (q.status === "validation_failed") return { level: "judged", failed: true, note: q.judge_notes };
    const ans = q.options ? q.options[q.answer] : q.answer ? "True" : "False";
    if (q.solution_program) return { level: "proven", program: q.solution_program, output: ans, tests: 0, misconceptions: q.wrong };
    const flags = Object.values(q.judges).filter((v) => v === "flag").length;
    return {
      level: flags >= 2 || !q.quote ? "judged" : "supported",
      quotes: q.quote ? [{ text: q.quote, section: q.source.section, found: true }] : [],
      solvers: { agree: flags >= 2 ? 2 : 3, total: 3, models: "2 model families" },
      note: !q.quote ? "Not checked yet: it hasn't been through the answer checks." : flags >= 2 ? "One solver picked a different answer, so it fell back to AI-reviewed only. Read it closely." : "",
      misconceptions: q.wrong,
    };
  };

  // ---- Coverage (approved questions per subtopic × difficulty) -----------------------------
  topics.forEach((t) => t.subtopics.forEach((s) => { M.coverage[s.id] = { easy: 0, medium: 0, hard: 0 }; }));
  bioQuestions.filter((q) => q.status === "approved").forEach((q) => { M.coverage[q.subtopic_id][q.difficulty]++; });
  const cells = topics.flatMap((t) => t.subtopics.flatMap((s) => Object.values(M.coverage[s.id])));
  const coveragePct = Math.round((100 * cells.filter((n) => n >= 2).length) / cells.length);

  // ---- Students: 61 in three sections -------------------------------------------------------
  const FN = ["Amara", "Bilal", "Chloe", "Diego", "Esme", "Femi", "Gabriel", "Hana", "Isaac", "Jade", "Kofi", "Lena", "Marco", "Nadia", "Omar", "Paige",
    "Ravi", "Sofia", "Theo", "Ursula", "Vik", "Willa", "Xavier", "Yara", "Zain", "Anya", "Bruno", "Camila", "Dario", "Ella", "Felix"];
  const LN = ["Ahmed", "Becker", "Castro", "Dubois", "Eze", "Ferrari", "Gupta", "Hansen", "Ito", "Jensen", "Khan", "Larsen", "Mendez", "Novak", "Ortiz",
    "Park", "Quinn", "Reyes", "Sato", "Torres", "Ueda", "Vargas", "Wright", "Xu", "Young", "Zimmer", "Abbott", "Bose", "Chandra"];
  const released = ["bio-t1", "bio-t2", "bio-t3"];
  const bioStudents = Array.from({ length: 61 }, (_, i) => {
    const class_id = i < 24 ? "c3" : i < 46 ? "c4" : "c5";
    const honors = class_id === "c5";
    const f = FN[i % FN.length], l = LN[(i * 7) % LN.length];
    const ability = (rand() - 0.5) * 0.4 + (honors ? 0.12 : 0);
    const mastery = {};
    topics.forEach((t, k) => {
      const base = [0.74, 0.63, 0.44][k];
      mastery[t.id] = base === undefined ? 0 : r2(Math.max(0.08, Math.min(0.97, base + ability + (rand() - 0.5) * 0.25)));
    });
    const avg = r2(mean(released.map((t) => mastery[t])));
    const third = topics[2].subtopics.map((s) => s.name);
    return {
      id: `s${101 + i}`, name: `${f} ${l}`, email: `${f.toLowerCase()}.${l.toLowerCase()}@example.edu`,
      class_id, course: "biology",
      sessions: 2 + Math.floor(rand() * 10), attempts: 18 + Math.floor(rand() * 120),
      last_active: `2026-09-${String(16 + Math.floor(rand() * 15)).padStart(2, "0")}`,
      mastery, avg_mastery: avg,
      trend: Array.from({ length: 8 }, (_, w) => r2(Math.min(0.95, Math.max(0.1, avg - 0.32 + w * 0.045 + (rand() - 0.5) * 0.06)))),
      weak_subtopics: ["Glycolysis", pick(third.filter((n) => n !== "Glycolysis"))],
    };
  });
  M.students.push(...bioStudents);

  // ---- Course -----------------------------------------------------------------------------
  const approved = bioQuestions.filter((q) => q.status === "approved");
  const biology = {
    id: "biology", code: "BIOL 190", name: "Intro Biology", term: "Fall 2026", subject: "biology",
    question_types: ["multiple_choice", "true_false"], owner: "u1", collaborators: [],
    taxonomy: topics, taxonomy_versions: [
      { id: "b1", label: "v1 · drafted from OpenStax Biology 2e", status: "approved", active: true, topics: 6, subtopics: 19, created: "2026-08-24", source: "Drafted with AI" },
    ],
    coverage_target: 2,
    setup: { materials: "done", taxonomy: "done", coverage: "in_progress", review: "in_progress", question_set: "done", classes: "done" },
    numbers: {
      questions: bioQuestions.length, approved: approved.length,
      awaiting_review: bioQuestions.filter((q) => q.status === "validation_passed").length,
      students: bioStudents.length, avg_mastery: r2(mean(bioStudents.map((s) => s.avg_mastery))), coverage_pct: coveragePct,
    },
  };
  // Running courses first: Python, Biology, then Statistics (still being set up).
  M.courses.splice(1, 0, biology);

  M.books_sections.b4 = [
    { number: "7", title: "Cellular respiration", sections: ["7.1 Energy in living systems", "7.2 Glycolysis", "7.3 Oxidation of pyruvate", "7.4 Oxidative phosphorylation"]
      .map((t, k) => ({ id: `b4-7-${k + 1}`, title: t, confidence: "high", words: 1400 + k * 230, questions: [2, 4, 0, 3][k] })) },
    { number: "11", title: "Meiosis and sexual reproduction", sections: ["11.1 The process of meiosis", "11.2 Sexual reproduction"]
      .map((t, k) => ({ id: `b4-11-${k + 1}`, title: t, confidence: "high", words: 1800 + k * 300, questions: [2, 0][k] })) },
  ];

  // ---- Classes and question sets ------------------------------------------------------------
  const unit13 = approved.filter((q) => released.includes(q.topic_id)).map((q) => q.id);
  const honorsExtra = approved.filter((q) => q.topic_id === "bio-t5").map((q) => q.id);
  M.classes.push(
    { id: "c3", course: "biology", name: "Section 001 (Mon/Wed/Fri)", join_code: "BIO-7RW", question_set: "qs3", students: 24, restrict_roster: false, created: "2026-08-31" },
    { id: "c4", course: "biology", name: "Section 002 (Tue/Thu)", join_code: "BIO-K2M", question_set: "qs3", students: 22, restrict_roster: false, created: "2026-08-31" },
    { id: "c5", course: "biology", name: "Section H01 (honors, Mon/Wed/Fri)", join_code: "BIO-H9P", question_set: "qs4", students: 15, restrict_roster: false, created: "2026-09-02" },
  );
  M.question_sets.push(
    { id: "qs3", course: "biology", name: "Units 1–3 practice", frozen: "2026-09-21", questions: unit13.length, coverage_pct: coveragePct, classes: ["c3", "c4"], status: "published" },
    { id: "qs4", course: "biology", name: "Honors: units 1–3 + genetics", frozen: "2026-09-21", questions: unit13.length + honorsExtra.length, coverage_pct: coveragePct, classes: ["c5"], status: "published" },
  );
  if (M.question_set_members) Object.assign(M.question_set_members, { qs3: unit13, qs4: [...unit13, ...honorsExtra] });
  if (M.question_set_frozen_count) Object.assign(M.question_set_frozen_count, { qs3: unit13.length, qs4: unit13.length + honorsExtra.length });
  if (M.freeze_preview) M.freeze_preview.biology = { approved: approved.length, coverage_pct: coveragePct, added_since_last: 0, edited_since_last: 0 };
  if (M.course_counts) M.course_counts.biology = { books: 1, taxonomy_versions: 1, learned_rules: 2 };

  // ---- Schedule -----------------------------------------------------------------------------
  const W1 = new Date("2026-08-31T12:00:00");
  const ws = (w) => { const d = new Date(W1); d.setDate(d.getDate() + (w - 1) * 7); return d.toISOString().slice(0, 10); };
  const plan = [
    [1, "Chemistry of life", ["bio-t1"]], [2, "Cells and membranes", ["bio-t2"]], [3, "Lab week: diffusion and osmosis", [], "Lab"],
    [4, "Energy in cells", ["bio-t3"]], [5, "Respiration and photosynthesis", []], [6, "Cell division", ["bio-t4"]],
    [7, "Review", [], "Review week"], [8, "Midterm (Thu Oct 22)", [], "Midterm exam"], [9, "Mendelian genetics", ["bio-t5"]],
    [10, "Genetics II", []], [11, "DNA and replication", ["bio-t6"]], [12, "Gene expression", []],
    [13, "Lab week", [], "Lab"], [14, "Thanksgiving (no class Thu–Fri)", [], "Holiday"], [15, "Review", [], "Review week"],
  ];
  if (M.schedule) M.schedule.biology = {
    term: { name: "Fall 2026", starts: "2026-08-31", ends: "2026-12-11", final_exam: "2026-12-15" },
    release_mode: "schedule", current_week: 5, review_share: 0.2,
    weeks: plan.map(([week, title, tps, note]) => ({ week, title, starts: ws(week), topics: tps, note: note || "" })),
  };

  // ---- Assignments and per-student results ----------------------------------------------------
  const A = (o) => ({ course: "biology", points: 10, sections: ["c3", "c4", "c5"], late: { days: 2, penalty: 0.2 }, lms: null, goal: { type: "mastery", target: 0.7 }, ...o });
  const bioAssignments = [
    A({ id: "ba1", name: "Week 1: Chemistry of life", topics: ["bio-t1"], opens: "2026-08-31", due: "2026-09-04", status: "closed", lms: { synced: "2026-09-08 08:00" } }),
    A({ id: "ba2", name: "Week 2: Cells and membranes", topics: ["bio-t2"], opens: "2026-09-07", due: "2026-09-11", status: "closed", lms: { synced: "2026-09-15 08:00" } }),
    A({ id: "ba3", name: "Week 4: Energy in cells", topics: ["bio-t3"], opens: "2026-09-21", due: "2026-09-25", status: "closed", lms: { synced: "2026-09-29 08:00" } }),
    A({ id: "ba4", name: "Week 5: Cellular respiration", topics: ["bio-t3"], opens: "2026-09-28", due: "2026-10-02", status: "open", lms: { synced: null } }),
    A({ id: "ba5", name: "Week 6: Cell division", topics: ["bio-t4"], opens: "2026-10-05", due: "2026-10-09", status: "draft" }),
  ];
  M.assignments.push(...bioAssignments);
  if (M.assignment_min_level) bioAssignments.forEach((a) => { M.assignment_min_level[a.id] = "supported"; });
  const bioExt = [{ student: "s112", assignment: "ba4", due: "2026-10-05", reason: "Accommodation letter" }];
  M.extensions.push(...bioExt);
  if (M.student_notes) M.student_notes.s112 = "Accommodation letter (Disability Resource Center): +3 days on practice deadlines.";
  bioStudents.forEach((s) => {
    M.assignment_results[s.id] = {};
    bioAssignments.forEach((a) => {
      const ext = bioExt.find((e) => e.student === s.id && e.assignment === a.id);
      const r = { progress: 0, state: "not_started", score: null, submitted: null, extension: ext ? ext.due : null };
      if (a.status === "closed") {
        const x = rand();
        if (x < 0.45 + 0.55 * s.avg_mastery) {
          const late = rand() < 0.1;
          Object.assign(r, { progress: 1, state: late ? "late" : "done", submitted: late ? "after due" : "on time", score: a.points * (late ? 0.8 : 1) });
        } else if (x < 0.95) {
          const p = r2(0.35 + rand() * 0.55);
          Object.assign(r, { progress: p, state: "partial", score: Math.round(a.points * p * 10) / 10 });
        } else Object.assign(r, { progress: 0, state: "missed", score: 0 });
      } else if (a.status === "open") {
        const x = rand() - (s.class_id === "c5" ? 0.12 : 0);
        if (x < 0.22) Object.assign(r, { progress: 1, state: "done", score: a.points, submitted: "on time" });
        else if (x < 0.74) Object.assign(r, { progress: r2(0.2 + rand() * 0.7), state: "in_progress" });
      }
      M.assignment_results[s.id][a.id] = r;
    });
  });
  const cnt = (st) => bioStudents.filter((s) => M.assignment_results[s.id].ba4.state === st).length;

  // ---- Insights (week 5) ------------------------------------------------------------------
  const qid = (prompt) => bioQuestions.find((q) => q.prompt.startsWith(prompt)).id;
  const iGly = qid("Glycolysis requires oxygen"), iEtc = qid("What is the final electron"), iAtp = qid("ATP is the cell's"),
    iPho = qid("The O₂ released"), iTon = qid("A red blood cell");
  const active = cnt("done") + cnt("in_progress");
  M.insights.biology = {
    week: 5, range: "Sep 28 – Oct 4", students_active: active, attempts: active * 41,
    misconceptions: [
      { question_id: iGly, subtopic: "Glycolysis", topic: "Energy in cells", attempts: 88, correct: 0.52, top_wrong: "True", top_wrong_share: 0.44,
        by_section: { c3: 0.47, c4: 0.49, c5: 0.31 }, reading: "Thinks glycolysis needs oxygen because respiration does." },
      { question_id: iEtc, subtopic: "Cellular respiration", topic: "Energy in cells", attempts: 74, correct: 0.58, top_wrong: "NAD⁺", top_wrong_share: 0.33,
        by_section: { c3: 0.35, c4: 0.36, c5: 0.24 }, reading: "Confuses the electron carriers with the final acceptor." },
      { question_id: iPho, subtopic: "Photosynthesis", topic: "Energy in cells", attempts: 69, correct: 0.61, top_wrong: "True", top_wrong_share: 0.39,
        by_section: { c3: 0.41, c4: 0.42, c5: 0.3 }, reading: "Thinks the oxygen released comes from CO₂, not water." },
      { question_id: iAtp, subtopic: "ATP", topic: "Energy in cells", attempts: 63, correct: 0.67, top_wrong: "True", top_wrong_share: 0.33,
        by_section: { c3: 0.36, c4: 0.35, c5: 0.22 }, reading: "Treats ATP as a long-term energy store." },
      { question_id: iTon, subtopic: "Membranes and transport", topic: "Cells", attempts: 51, correct: 0.71, top_wrong: "It swells and may burst", top_wrong_share: 0.24,
        by_section: { c3: 0.26, c4: 0.27, c5: 0.15 }, reading: "Reverses hypertonic and hypotonic." },
    ],
    improved: [
      { subtopic: "Organelles", topic: "Cells", from: 0.55, to: 0.74 },
      { subtopic: "Enzymes", topic: "Chemistry of life", from: 0.49, to: 0.66 },
    ],
    weekly_active: [55, 57, 49, 54, active],
  };
  const per = (cls) => {
    const ss = bioStudents.filter((s) => s.class_id === cls);
    const act = ss.filter((s) => ["done", "in_progress"].includes(M.assignment_results[s.id].ba4.state)).length;
    return { students_active: act, attempts: act * 41, weekly_active: [Math.round(ss.length * 0.9), Math.round(ss.length * 0.93), Math.round(ss.length * 0.8), Math.round(ss.length * 0.88), act] };
  };
  // MOCK.run (data-g-run.js) only loads on the pages that use it.
  if (M.run) Object.assign(M.run.by_section, { c3: per("c3"), c4: per("c4"), c5: per("c5") });
  if (M.run) Object.assign(M.run.distribution, {
    [iGly]: [["True", 0.44], ["False", 0.52], ["No answer (skipped)", 0.04]],
    [iEtc]: [["NAD⁺", 0.33], ["Oxygen", 0.58], ["Water", 0.06], ["Carbon dioxide", 0.03]],
    [iPho]: [["True", 0.39], ["False", 0.61]],
    [iAtp]: [["True", 0.33], ["False", 0.67]],
    [iTon]: [["It swells and may burst", 0.24], ["It shrinks as water leaves", 0.71], ["Nothing; water moves equally both ways", 0.04], ["It pumps salt in to match", 0.01]],
  });

  // ---- Reports ----------------------------------------------------------------------------
  const iX = qid("A carrier mother"), iDup = qid("Which molecule carries");
  M.reports.push(
    { id: "r7", question_id: iX, student: "s131", reason: "unclear", at: "2026-09-30 08:12", status: "open",
      text: "Does it matter whether the father has the trait? It says unaffected, but I wasn't sure it mattered for a son.", answer: "1/4" },
    { id: "r6", question_id: iDup, student: "s104", reason: "typo", at: "2026-09-22 14:40", status: "resolved",
      text: "I think I got almost this exact question twice in one session.", answer: "tRNA",
      resolution: { action: "dismissed", by: "Maya Chen", at: "2026-09-22 17:05", reply: "You're right: it duplicated another question, so I removed it from practice." } },
  );
  if (M.run) Object.assign(M.run.question_reach, {
    [iX]: { attempts: 38, students: 31, sets: ["Honors: units 1–3 + genetics"] },
    [iDup]: { attempts: 12, students: 11, sets: ["Units 1–3 practice"] },
  });

  // ---- Student detail: attempts for Biology students -----------------------------------------
  const baseAttempts = M.attemptsFor;
  const cache = {};
  M.attemptsFor = function (studentId) {
    const s = M.student(studentId);
    if (!s || s.course !== "biology") return baseAttempts ? baseAttempts(studentId) : { attempts: [], sessions: [], weak: [] };
    if (cache[studentId]) return cache[studentId];
    let sd = Number(studentId.slice(1)) * 131;
    const rr = () => ((sd = (sd * 16807) % 2147483647) - 1) / 2147483646;
    const lastDay = Number(s.last_active.slice(8));
    const sessions = Array.from({ length: s.sessions }, (_, k) => {
      const day = Math.max(1, lastDay - (s.sessions - 1 - k) * 2);
      const served = 4 + Math.floor(rr() * 10);
      return { id: 600 + Number(studentId.slice(1)) * 20 + k, set: s.class_id === "c5" ? "Honors: units 1–3 + genetics" : "Units 1–3 practice",
        started: `2026-09-${String(day).padStart(2, "0")} ${String(9 + Math.floor(rr() * 10)).padStart(2, "0")}:${String(Math.floor(rr() * 60)).padStart(2, "0")}`,
        served, answered: served, status: "closed" };
    });
    const pool = approved.filter((q) => s.mastery[q.topic_id] > 0);
    const attempts = Array.from({ length: Math.min(14, s.attempts) }, (_, k) => {
      const q = pool[Math.floor(rr() * pool.length)];
      const day = Math.max(1, lastDay - Math.floor(k / 4));
      return { id: 9500 + k, question_id: q.id, prompt: q.prompt, type: q.type, topic: q.topic, subtopic: q.subtopic, difficulty: q.difficulty,
        score: rr() < s.mastery[q.topic_id] ? 100 : 0, at: `2026-09-${String(day).padStart(2, "0")} ${String(20 - (k % 4) * 2).padStart(2, "0")}:${String(10 + k * 3).padStart(2, "0")}` };
    });
    const weak = s.weak_subtopics.map((name, i) => ({ name, weakness: r2(0.74 - i * 0.12) }));
    return (cache[studentId] = { attempts, sessions, weak });
  };

  // ---- Term report, activity, jobs ------------------------------------------------------------
  if (M.term_report) M.term_report.biology = {
    as_of: "2026-09-30", week: 5, weeks: 15, final_after: "2026-12-15",
    enrolment: { first_day: 63, added: 0, dropped: 2, drop_deadline: "2026-09-11", now: 61, dropped_note: "2 students dropped before the Sep 11 deadline." },
    reports_median_hours: 6.5, generated: bioQuestions.length, rejected_reasons: [["Ambiguous", 1], ["Too similar to another question", 1]],
  };
  const honorsDone = bioStudents.filter((s) => s.class_id === "c5" && M.assignment_results[s.id].ba4.state === "done").length;
  if (M.activity) M.activity.splice(1, 0,
    { when: "1 h ago", course: "biology", who: "Honors section", text: `has ${honorsDone} of 15 at the Week 5 goal already`, file: "classes.html" },
    { when: "Yesterday", course: "biology", who: "Maya Chen", text: "approved 6 questions in Energy in cells", file: "review.html" });
  M.jobs.push({ id: "j10", course: "biology", kind: "Generate for gaps", detail: "Cell division · 4 cells", status: "done", progress: 1, started: "Sep 29, 16:20", by: "Maya Chen", result: "6 questions, 6 passed checks" });

  // ---- This week, per running course (My courses) ------------------------------------------
  const week = {};
  const py = M.course("python");
  const due = M.assignments.find((a) => a.course === "python" && a.status === "open");
  if (due) {
    const n = { done: 0, in_progress: 0, not_started: 0 };
    M.students.filter((s) => s.course === "python").forEach((s) => {
      const r = M.assignment_results[s.id][due.id];
      n[r.state === "done" || r.state === "late" ? "done" : r.state === "in_progress" ? "in_progress" : "not_started"]++;
    });
    const top = M.insights.python.misconceptions[0];
    week.python = {
      week: 5, due: due.name, due_date: "Fri, Oct 2", ...n, total: py.numbers.students,
      mistake: `${Math.round(top.top_wrong_share * 100)}% on ${top.subtopic}: ${top.reading.charAt(0).toLowerCase()}${top.reading.slice(1).replace(/\.$/, "")}`,
      reports: M.reports.filter((r) => r.status === "open" && M.question(r.question_id)?.course === "python").length, sections: 2,
    };
  }
  week.biology = {
    week: 5, due: "Week 5: Cellular respiration", due_date: "Fri, Oct 2", done: cnt("done"), in_progress: cnt("in_progress"), not_started: cnt("not_started"),
    total: bioStudents.length, mistake: "44% on Glycolysis: think it needs oxygen", reports: 1, sections: 3,
  };
  M.course_week = week;
})();
