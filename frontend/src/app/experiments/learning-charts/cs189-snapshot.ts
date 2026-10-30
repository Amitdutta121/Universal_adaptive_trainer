/**
 * CS189's scored answers, copied from the dev database on 2026-10-25 (course 4, 64 answers, 24
 * students), oldest first. Student ids are the database ids, nothing else about them is kept.
 *
 * TODO(real): a snapshot, not live. The real chart reads these rows from an API endpoint; this
 * file only lets the prototype show what today's data looks like through the same analysis.
 */

import type { Answer, Difficulty } from "./learning-analysis";

const SUBTOPICS = ["Conditionals", "Literals and types", "Loop control statements", "Loops and iteration", "Using the REPL and basic tooling", "Variables and expressions"];

/** [student, subtopic index, served difficulty, correct, answered at (UTC)], oldest first. */
const ROWS: [string, number, Difficulty, boolean, string][] = [
  ["s39", 4, "easy", true, "2026-10-16T18:33:02Z"],
  ["s39", 4, "easy", true, "2026-10-16T18:39:48Z"],
  ["s39", 4, "medium", false, "2026-10-16T18:40:41Z"],
  ["s39", 4, "easy", true, "2026-10-16T18:41:53Z"],
  ["s39", 4, "easy", true, "2026-10-16T18:43:33Z"],
  ["s39", 4, "medium", true, "2026-10-16T18:47:38Z"],
  ["s39", 5, "easy", true, "2026-10-16T18:49:24Z"],
  ["s40", 4, "easy", false, "2026-10-23T17:58:00Z"],
  ["s41", 4, "easy", false, "2026-10-23T18:02:32Z"],
  ["s42", 4, "easy", false, "2026-10-23T18:40:01Z"],
  ["s43", 4, "easy", false, "2026-10-23T18:40:33Z"],
  ["s44", 4, "easy", false, "2026-10-23T19:21:10Z"],
  ["s44", 4, "easy", true, "2026-10-23T19:21:28Z"],
  ["s44", 4, "easy", false, "2026-10-23T19:21:47Z"],
  ["s44", 4, "easy", true, "2026-10-23T19:22:05Z"],
  ["s45", 4, "easy", false, "2026-10-23T19:25:07Z"],
  ["s45", 4, "easy", true, "2026-10-23T19:25:25Z"],
  ["s45", 4, "easy", false, "2026-10-23T19:25:44Z"],
  ["s45", 4, "easy", true, "2026-10-23T19:26:02Z"],
  ["s46", 4, "easy", false, "2026-10-23T19:29:14Z"],
  ["s46", 4, "easy", true, "2026-10-23T19:29:32Z"],
  ["s46", 4, "easy", false, "2026-10-23T19:29:51Z"],
  ["s46", 4, "easy", true, "2026-10-23T19:30:14Z"],
  ["s46", 4, "easy", false, "2026-10-23T19:30:42Z"],
  ["s46", 4, "easy", true, "2026-10-23T19:31:16Z"],
  ["s46", 4, "easy", false, "2026-10-23T19:31:47Z"],
  ["s46", 4, "easy", true, "2026-10-23T19:32:14Z"],
  ["s46", 4, "easy", false, "2026-10-23T19:32:42Z"],
  ["s46", 4, "easy", true, "2026-10-23T19:33:12Z"],
  ["s47", 4, "easy", false, "2026-10-24T03:27:02Z"],
  ["s48", 4, "easy", false, "2026-10-25T02:22:11Z"],
  ["s49", 4, "easy", false, "2026-10-25T02:22:46Z"],
  ["s50", 4, "easy", false, "2026-10-25T02:24:58Z"],
  ["s51", 4, "easy", false, "2026-10-25T02:25:31Z"],
  ["s52", 4, "easy", false, "2026-10-25T02:28:25Z"],
  ["s53", 4, "easy", false, "2026-10-25T02:28:57Z"],
  ["s54", 4, "easy", false, "2026-10-25T02:29:37Z"],
  ["s55", 4, "easy", false, "2026-10-25T02:30:09Z"],
  ["s57", 4, "easy", false, "2026-10-25T02:31:11Z"],
  ["s58", 4, "easy", false, "2026-10-25T02:31:43Z"],
  ["s60", 4, "easy", false, "2026-10-25T02:33:37Z"],
  ["s61", 4, "easy", false, "2026-10-25T02:34:10Z"],
  ["s62", 4, "easy", false, "2026-10-25T03:21:31Z"],
  ["s63", 4, "easy", false, "2026-10-25T03:22:14Z"],
  ["s64", 4, "easy", true, "2026-10-25T23:23:38Z"],
  ["s64", 4, "easy", true, "2026-10-25T23:23:53Z"],
  ["s64", 4, "medium", false, "2026-10-25T23:24:21Z"],
  ["s64", 4, "easy", true, "2026-10-25T23:24:30Z"],
  ["s64", 4, "easy", false, "2026-10-25T23:24:47Z"],
  ["s64", 4, "easy", true, "2026-10-25T23:25:32Z"],
  ["s64", 4, "easy", true, "2026-10-25T23:26:12Z"],
  ["s64", 4, "easy", false, "2026-10-25T23:27:12Z"],
  ["s64", 4, "easy", true, "2026-10-25T23:27:44Z"],
  ["s64", 4, "easy", true, "2026-10-25T23:28:43Z"],
  ["s64", 4, "medium", true, "2026-10-25T23:29:08Z"],
  ["s64", 5, "easy", true, "2026-10-25T23:30:01Z"],
  ["s64", 5, "easy", true, "2026-10-25T23:31:09Z"],
  ["s64", 1, "easy", true, "2026-10-25T23:31:42Z"],
  ["s64", 0, "hard", false, "2026-10-25T23:35:48Z"],
  ["s64", 2, "medium", false, "2026-10-25T23:37:00Z"],
  ["s64", 3, "medium", false, "2026-10-25T23:38:17Z"],
  ["s64", 3, "easy", false, "2026-10-25T23:43:18Z"],
  ["s64", 3, "easy", false, "2026-10-25T23:44:26Z"],
  ["s64", 3, "easy", false, "2026-10-25T23:45:37Z"],
];

export const CS189_SNAPSHOT: Answer[] = ROWS.map(([student, subtopic, difficulty, correct, at]) => ({
  student,
  subtopic: SUBTOPICS[subtopic],
  difficulty,
  correct,
  at,
}));
