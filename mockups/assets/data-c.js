/*
 * Extra mock data for group C (materials, taxonomy, coverage pages). Loaded right after
 * mock-data.js. Only ADDS fields to window.MOCK; never changes existing ones.
 * TODO(real): every value in this file is invented.
 */
(function () {
  const M = window.MOCK;

  // TODO(real): uploaded filenames and sizes per book (provenance card).
  M.book_files = {
    b1: { filename: "think-python-3e.pdf", size: "4.81 MB", producer: "pdf outline reader" },
    b2: { filename: "py4e-book.json", size: "1.27 MB", producer: "assistant (book guide v1)" },
    b3: { filename: "openintro-statistics-4e.pdf", size: "18.40 MB", producer: "pdf outline reader" },
  };

  // TODO(real): OpenIntro Statistics outline (chapter titles are the real book's; section
  // list shortened). The first 41 sections are embedded, matching MOCK.books b3 (41/64).
  const statsChapters = [
    ["1", "Introduction to data", ["1.1 Case study: using stents to prevent strokes", "1.2 Data basics", "1.3 Sampling principles and strategies", "1.4 Experiments"]],
    ["2", "Summarizing data", ["2.1 Examining numerical data", "2.2 Considering categorical data", "2.3 Case study: malaria vaccine"]],
    ["3", "Probability", ["3.1 Defining probability", "3.2 Conditional probability", "3.3 Sampling from a small population", "3.4 Random variables", "3.5 Continuous distributions"]],
    ["4", "Distributions of random variables", ["4.1 Normal distribution", "4.2 Geometric distribution", "4.3 Binomial distribution", "4.4 Negative binomial distribution", "4.5 Poisson distribution"]],
    ["5", "Foundations for inference", ["5.1 Point estimates and sampling variability", "5.2 Confidence intervals for a proportion", "5.3 Hypothesis testing for a proportion"]],
    ["6", "Inference for categorical data", ["6.1 Inference for a single proportion", "6.2 Difference of two proportions", "6.3 Testing for goodness of fit using chi-square", "6.4 Testing for independence in two-way tables"]],
    ["7", "Inference for numerical data", ["7.1 One-sample means with the t-distribution", "7.2 Paired data", "7.3 Difference of two means", "7.4 Power calculations for a difference of means", "7.5 Comparing many means with ANOVA"]],
    ["8", "Introduction to linear regression", ["8.1 Fitting a line, residuals, and correlation", "8.2 Least squares regression", "8.3 Types of outliers in linear regression", "8.4 Inference for linear regression"]],
    ["9", "Multiple and logistic regression", ["9.1 Introduction to multiple regression", "9.2 Model selection", "9.3 Checking model conditions using graphs", "9.4 Multiple regression case study", "9.5 Introduction to logistic regression"]],
  ];
  let n = 0;
  M.books_sections.b3 = statsChapters.map(([num, title, secs]) => ({
    number: num, title,
    sections: secs.map((s, k) => {
      n++;
      return {
        id: `b3-${num}-${k + 1}`, title: s, confidence: num === "2" && k === 2 ? "medium" : "high",
        words: 900 + ((n * 373) % 2600), questions: 0,
        // Only 38 sections listed here; embedding share scaled to 41/64.
        embedded: n <= Math.round((38 * 41) / 64),
      };
    }),
  }));

  // TODO(real): which questions are grounded in which section. The base mock attributes
  // every question to 9.11; here only the Aliasing questions count as "from this section".
  M.section_questions = {
    "b1-9-5": M.questions.filter((q) => q.subtopic === "Aliasing").map((q) => q.id),
  };

  // TODO(real): why the AI flagged a draft row, and where each proposed subtopic came from.
  M.draft_notes = {
    "Margin of error": "Overlaps “Standard error” (Sampling distributions). Consider merging or making it about interpreting a stated margin.",
  };
  M.draft_source_sections = {
    "Describing data": "ch. 2 Summarizing data",
    "Probability": "ch. 3 Probability",
    "Random variables": "ch. 3.4 Random variables, 4.3 Binomial",
    "Normal distribution": "ch. 4.1 Normal distribution",
    "Sampling distributions": "ch. 5.1 Point estimates and sampling variability",
    "Confidence intervals": "ch. 5.2, 6.1, 7.1",
    "Hypothesis tests": "ch. 5.3, 7.1",
    "Regression": "ch. 8 Introduction to linear regression",
  };

  // TODO(real): estimated LLM cost per generated question (generation + 4 judges).
  M.cost_per_question_usd = 0.034;
})();
