/*
 * Additions to the lesson block contract (assets/lesson-schema.js), all optional and
 * backward compatible:
 *   branch.remediation["<k>"].misconception   the misconception wrong option k reveals; falls back
 *                                             to the block-level branch.misconception.
 * Editor-only fields the student player can ignore: stale, error, verified.
 * TODO(real): misconception labels come from the subtopic's misconception tags and Insights.
 */
(function () {
  const M = window.MOCK;
  M.branchMisconception = (b, k) => (b.remediation || {})[String(k)]?.misconception || b.misconception || "";
})();
