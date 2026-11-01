/**
 * Biology. TODO(real): mining output, templates and examples come from the mining and
 * suggestion calls; the taxonomy and "have" counts are invented for the prototype.
 */

import type { Domain } from "./mock-types";

const h = (easy: number, medium: number, hard = 0) => ({ easy, medium, hard });

export const BIOLOGY: Domain = {
  id: "biology",
  subjectLabel: "Biology",
  course: "BIO 101 · Principles of Biology",
  book: {
    title: "Biology 2e (OpenStax)",
    author: "Clark, Douglas, Choi et al.",
    pages: 1488,
    chapters: 47,
    sections: 296,
  },
  taxonomy: { label: "Cells, energy and genetics", topics: 9, subtopics: 23 },
  questionTypes: {
    multiple_choice: "Multiple choice",
    true_false: "True / false",
    short_answer: "Short answer",
  },
  mining: {
    tocTokens: 9_120,
    sectionsRouted: 58,
    sections: [
      { title: "Review Questions", count: 14, kind: "review" },
      { title: "Critical Thinking Questions", count: 14, kind: "conceptual" },
      { title: "Visual Connection Questions", count: 14, kind: "conceptual" },
      { title: "Learning Objectives", count: 15, kind: "objectives" },
      { title: "Answer Key", count: 1, kind: "answers" },
    ],
    itemsFound: 538,
    level: "Introductory undergraduate, majors",
    taskMix: [
      { label: "Recall a term or fact", share: 0.41 },
      { label: "Apply to a scenario", share: 0.27 },
      { label: "Explain or justify", share: 0.18 },
      { label: "Interpret a figure", share: 0.14 },
    ],
    difficultyMix: { easy: 221, medium: 205, hard: 112 },
    samples: [
      {
        text: "Which of the following is not a component of the plasma membrane?",
        source: "Ch 5 · Review Questions · Q 1",
        inferredType: "Multiple choice",
        difficulty: "easy",
      },
      {
        text: "During which stage of the cell cycle do sister chromatids separate?",
        source: "Ch 10 · Review Questions · Q 8",
        inferredType: "Multiple choice",
        difficulty: "easy",
      },
      {
        text: "Why does a red blood cell placed in distilled water burst?",
        source: "Ch 5 · Critical Thinking Questions · Q 24",
        inferredType: "Multiple choice",
        difficulty: "medium",
      },
      {
        text: "If a pea plant heterozygous for seed colour is self-crossed, what fraction of offspring will be homozygous recessive?",
        source: "Ch 12 · Review Questions · Q 12",
        inferredType: "Short answer",
        difficulty: "medium",
      },
      {
        text: "Explain what would happen to ATP production if the inner mitochondrial membrane became permeable to protons.",
        source: "Ch 7 · Critical Thinking Questions · Q 31",
        inferredType: "Multiple choice",
        difficulty: "hard",
      },
      {
        text: "Using Figure 14.13, predict the banding pattern after two rounds of replication.",
        source: "Ch 14 · Visual Connection Questions · Q 3",
        inferredType: "Needs a figure",
        difficulty: "hard",
      },
    ],
    notes: [
      "Only chapters 2 to 15 were read: the rest of the book is not in your taxonomy.",
      "Visual Connection questions need the book's figures. They set the level, but no question style depends on a figure.",
      "Critical Thinking questions ask for a paragraph. Your course has no AI-graded written answers, so their ideas are turned into choice and short-answer styles.",
    ],
  },
  wishes: [
    "More scenario questions",
    "Experimental data",
    "Less pure recall",
    "Genetics problems",
  ],
  templates: [
    {
      id: "bi-e-recall",
      name: "Recall a key term or function",
      summary: "One fact students need before they can reason with it.",
      questionType: "multiple_choice",
      difficulty: "easy",
      checkedBy: "Choice: one correct option",
      evidence: "41% of the book's items are recall, mostly in Review Questions.",
      examples: [
        {
          prompt: "Which organelle produces most of the ATP in a eukaryotic cell?",
          options: [
            { text: "Mitochondrion", correct: true },
            { text: "Ribosome" },
            { text: "Golgi apparatus" },
            { text: "Lysosome" },
          ],
          grounding: "§4.3 Eukaryotic cells",
        },
        {
          prompt: "Which class of macromolecule stores hereditary information?",
          options: [
            { text: "Nucleic acids", correct: true },
            { text: "Proteins" },
            { text: "Lipids" },
            { text: "Carbohydrates" },
          ],
          grounding: "§3.5 Nucleic acids",
        },
      ],
    },
    {
      id: "bi-e-tf",
      name: "Catch a common misconception",
      summary: "One true-or-false statement built on something students often get backwards.",
      questionType: "true_false",
      difficulty: "easy",
      checkedBy: "Choice: true or false",
      evidence: "Several Review Questions target these exact confusions.",
      examples: [
        {
          prompt: "True or false: plant cells do not carry out cellular respiration because they photosynthesize.",
          options: [{ text: "True" }, { text: "False", correct: true }],
          grounding: "§7.1 Energy in living systems",
        },
        {
          prompt: "True or false: meiosis produces four genetically identical daughter cells.",
          options: [{ text: "True" }, { text: "False", correct: true }],
          grounding: "§11.1 The process of meiosis",
        },
      ],
    },
    {
      id: "bi-e-term",
      name: "Name the process or molecule",
      summary: "A short description; students type the one-word or short name.",
      questionType: "short_answer",
      difficulty: "easy",
      checkedBy: "Text match after normalising case and spacing; listed synonyms accepted",
      evidence: "Matches the Key Terms each chapter ends with.",
      examples: [
        {
          prompt: "What is the movement of water across a semipermeable membrane, toward the side with more solute, called?",
          answer: "osmosis",
          grounding: "§5.2 Passive transport",
        },
        {
          prompt: "Which molecule is the cell's main short-term energy currency? Give its abbreviation.",
          answer: "ATP (accepts: adenosine triphosphate)",
          grounding: "§6.4 ATP: Adenosine triphosphate",
        },
      ],
    },
    {
      id: "bi-m-scenario",
      name: "Apply a concept to a lab or body scenario",
      summary: "A concrete situation; students pick what happens and why.",
      questionType: "multiple_choice",
      difficulty: "medium",
      checkedBy: "Choice: one correct option",
      evidence: "27% of the book's items apply an idea to a scenario.",
      examples: [
        {
          prompt: "A red blood cell (about 0.9% salt inside) is placed in a 3% salt solution. What happens?",
          options: [
            { text: "Water leaves the cell and it shrinks", correct: true },
            { text: "Water enters the cell and it bursts" },
            { text: "Nothing: the membrane blocks water" },
            { text: "Salt enters until both sides are 3%" },
          ],
          grounding: "§5.2 Passive transport",
        },
        {
          prompt: "A human enzyme's activity drops sharply when the temperature rises from 37 °C to 60 °C. The best explanation is that:",
          options: [
            { text: "the enzyme's shape, including its active site, has changed", correct: true },
            { text: "the substrate has been used up" },
            { text: "the enzyme has turned into an inhibitor" },
            { text: "the reaction has become endergonic" },
          ],
          grounding: "§6.5 Enzymes",
        },
      ],
    },
    {
      id: "bi-m-seq",
      name: "Work out a sequence by base pairing",
      summary: "Students apply pairing rules to DNA or RNA and type the result.",
      questionType: "short_answer",
      difficulty: "medium",
      checkedBy: "Text match after removing spaces and 5′/3′ labels",
      evidence: "Matches the base-pairing items in chapters 14 and 15.",
      examples: [
        {
          prompt: "Write the complementary strand of 5′-ATGCCA-3′, read 5′ to 3′.",
          answer: "TGGCAT",
          grounding: "§14.2 DNA structure and sequencing",
        },
        {
          prompt: "An mRNA codon reads 5′-AUG-3′. What is the pairing tRNA anticodon, written 5′ to 3′?",
          answer: "CAU",
          grounding: "§15.4 Ribosomes and protein synthesis",
        },
      ],
    },
    {
      id: "bi-m-except",
      name: "Pick the one exception",
      summary: "Three true statements and one that does not belong. Students need the whole picture.",
      questionType: "multiple_choice",
      difficulty: "medium",
      checkedBy: "Choice: one correct option",
      evidence: "The book uses \"which is not\" questions in most Review sections.",
      examples: [
        {
          prompt: "Which of these is NOT found in prokaryotic cells?",
          options: [
            { text: "A nucleus", correct: true },
            { text: "Ribosomes" },
            { text: "A plasma membrane" },
            { text: "DNA" },
          ],
          grounding: "§4.2 Prokaryotic cells",
        },
        {
          prompt: "Which of these is NOT made by the light-dependent reactions of photosynthesis?",
          options: [
            { text: "Glucose", correct: true },
            { text: "ATP" },
            { text: "NADPH" },
            { text: "O₂" },
          ],
          grounding: "§8.2 The light-dependent reactions",
        },
      ],
    },
    {
      id: "bi-h-predict",
      name: "Predict the effect of a disruption",
      summary: "A drug, mutation or condition breaks one step; students trace what follows.",
      questionType: "multiple_choice",
      difficulty: "hard",
      checkedBy: "Choice: one correct option",
      evidence: "Turns the book's Critical Thinking questions into a gradable form.",
      examples: [
        {
          prompt: "Cyanide blocks complex IV (cytochrome c oxidase) of the electron transport chain. What happens in the mitochondrion?",
          options: [
            {
              text: "Electron transport stops, the proton gradient is not maintained, and ATP synthesis falls",
              correct: true,
            },
            { text: "Glycolysis stops at once, but the electron transport chain continues" },
            { text: "Oxygen use rises to make up for the block" },
            { text: "ATP synthase reverses and makes more ATP" },
          ],
          grounding: "§7.4 Oxidative phosphorylation",
        },
        {
          prompt: "A drug makes the inner mitochondrial membrane leaky to protons. Which outcome is expected?",
          options: [
            { text: "Oxygen is still used, but much less ATP is made", correct: true },
            { text: "ATP production rises" },
            { text: "Electron transport stops completely" },
            { text: "Glucose use by the cell falls" },
          ],
          grounding: "§7.4 Oxidative phosphorylation",
        },
      ],
    },
    {
      id: "bi-h-ratio",
      name: "Solve a cross: give the expected fraction",
      summary: "Two-gene or sex-linked crosses; students reason through the cross and give a fraction.",
      questionType: "short_answer",
      difficulty: "hard",
      checkedBy: "Text match on the fraction; equal decimals and percentages accepted",
      evidence: "Matches the genetics problems in chapters 12 and 13.",
      examples: [
        {
          prompt: "In peas, round (R) is dominant to wrinkled (r) and yellow (Y) to green (y). Two RrYy plants are crossed. What fraction of offspring are expected to be round and green?",
          answer: "3/16 (accepts 0.1875, 18.75%)",
          grounding: "§12.3 Laws of inheritance",
        },
        {
          prompt: "A woman who carries an X-linked recessive disorder has children with an unaffected man. What fraction of their sons are expected to be affected?",
          answer: "1/2 (accepts 0.5, 50%)",
          grounding: "§12.2 Characteristics and traits",
        },
      ],
    },
    {
      id: "bi-h-data",
      name: "Interpret experimental results",
      summary: "A small data set or a classic experiment, given in text; students pick the conclusion it supports.",
      questionType: "multiple_choice",
      difficulty: "hard",
      checkedBy: "Choice: one correct option",
      evidence: "Text-only versions of the book's Visual Connection questions.",
      examples: [
        {
          prompt: "An aquatic plant releases O₂ at these rates (mL/h) under increasing light: 0 lux: 0, 500: 4, 1000: 8, 2000: 11, 4000: 11. What best explains the plateau?",
          options: [
            {
              text: "Something other than light, such as CO₂ supply, has become limiting",
              correct: true,
            },
            { text: "Strong light has destroyed the chlorophyll" },
            { text: "The plant has switched to cellular respiration" },
            { text: "The O₂ is being reabsorbed by the leaves" },
          ],
          grounding: "§8.3 Using light energy to make organic molecules",
        },
        {
          prompt: "Bacteria grown in heavy ¹⁵N medium are moved to light ¹⁴N medium for exactly one round of DNA replication, then the DNA is spun in a density gradient. What is seen?",
          options: [
            { text: "One band, at an intermediate density", correct: true },
            { text: "One heavy band and one light band" },
            { text: "One heavy band only" },
            { text: "Three bands: heavy, intermediate and light" },
          ],
          grounding: "§14.3 Basics of DNA replication",
        },
      ],
    },
  ],
  reserve: [
    {
      id: "bi-h-tf",
      name: "Judge a claim that needs two ideas together",
      summary: "True or false, but only answerable by combining two concepts.",
      questionType: "true_false",
      difficulty: "hard",
      checkedBy: "Choice: true or false",
      evidence: "A quick hard style.",
      examples: [
        {
          prompt: "True or false: because sister chromatids are identical, crossing over during meiosis I cannot create new allele combinations.",
          options: [{ text: "True" }, { text: "False", correct: true }],
          grounding: "§11.1 The process of meiosis",
        },
        {
          prompt: "True or false: a cell with no mitochondria can still make ATP.",
          options: [{ text: "True", correct: true }, { text: "False" }],
          grounding: "§7.2 Glycolysis",
        },
      ],
    },
    {
      id: "bi-m-tf",
      name: "Decide whether a cause-and-effect claim holds",
      summary: "One statement linking a cause to an effect; students judge it.",
      questionType: "true_false",
      difficulty: "medium",
      checkedBy: "Choice: true or false",
      evidence: "A lighter medium style.",
      examples: [
        {
          prompt: "True or false: raising the substrate concentration can overcome a competitive inhibitor.",
          options: [{ text: "True", correct: true }, { text: "False" }],
          grounding: "§6.5 Enzymes",
        },
        {
          prompt: "True or false: a point mutation always changes the protein that is made.",
          options: [{ text: "True" }, { text: "False", correct: true }],
          grounding: "§14.6 DNA repair",
        },
      ],
    },
  ],
  topics: [
    {
      id: "chem",
      name: "Chemistry of Life",
      subtopics: [
        { id: "chem-1", name: "Water and hydrogen bonding", have: h(2, 1) },
        { id: "chem-2", name: "Biological macromolecules", have: h(3, 1) },
      ],
    },
    {
      id: "cell",
      name: "Cell Structure",
      subtopics: [
        { id: "cell-1", name: "Prokaryotic and eukaryotic cells", have: h(3, 2) },
        { id: "cell-2", name: "Organelles and their functions", have: h(4, 2) },
        { id: "cell-3", name: "The cytoskeleton", have: h(1, 0) },
      ],
    },
    {
      id: "mem",
      name: "Membranes and Transport",
      subtopics: [
        { id: "mem-1", name: "Membrane structure", have: h(2, 1) },
        { id: "mem-2", name: "Passive transport and osmosis", have: h(2, 2) },
        { id: "mem-3", name: "Active transport", have: h(1, 0) },
      ],
    },
    {
      id: "met",
      name: "Energy and Metabolism",
      subtopics: [
        { id: "met-1", name: "Enzymes", have: h(2, 1) },
        { id: "met-2", name: "ATP", have: h(2, 0) },
      ],
    },
    {
      id: "resp",
      name: "Cellular Respiration",
      subtopics: [
        { id: "resp-1", name: "Glycolysis", have: h(1, 1) },
        { id: "resp-2", name: "Citric acid cycle", have: h(1, 0) },
        { id: "resp-3", name: "Oxidative phosphorylation", have: h(0, 0) },
      ],
    },
    {
      id: "photo",
      name: "Photosynthesis",
      subtopics: [
        { id: "photo-1", name: "Light-dependent reactions", have: h(1, 1) },
        { id: "photo-2", name: "Calvin cycle", have: h(0, 0) },
      ],
    },
    {
      id: "div",
      name: "Cell Division",
      subtopics: [
        { id: "div-1", name: "Cell cycle and mitosis", have: h(2, 1) },
        { id: "div-2", name: "Meiosis", have: h(1, 1) },
      ],
    },
    {
      id: "gen",
      name: "Mendelian Genetics",
      subtopics: [
        { id: "gen-1", name: "Monohybrid crosses", have: h(1, 1) },
        { id: "gen-2", name: "Dihybrid crosses and independent assortment", have: h(0, 0) },
        { id: "gen-3", name: "Sex-linked and non-Mendelian inheritance", have: h(0, 0) },
      ],
    },
    {
      id: "dna",
      name: "DNA and Gene Expression",
      subtopics: [
        { id: "dna-1", name: "DNA structure and replication", have: h(2, 1) },
        { id: "dna-2", name: "Transcription", have: h(1, 0) },
        { id: "dna-3", name: "Translation", have: h(1, 0) },
      ],
    },
  ],
};
