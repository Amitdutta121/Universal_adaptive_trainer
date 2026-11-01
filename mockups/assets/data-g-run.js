/*
 * Page-only extras for G4 gradebook, G5 insights, G7 reports and the F3s refresher.
 * Load right after assets/data-g.js. Only ADDS to window.MOCK (under MOCK.run).
 * TODO(real): every value in this file is invented.
 */
(function () {
  const M = window.MOCK;

  // ---- G5: per-section activity this week. Sums match MOCK.insights.python. ----------------
  // TODO(real): aggregated from attempts per class.
  const by_section = {
    c1: { students_active: 11, attempts: 742, weekly_active: [13, 14, 13, 12, 11] },
    c2: { students_active: 8, attempts: 542, weekly_active: [9, 10, 10, 9, 8] },
  };

  // Answer distribution for each misconception question, for "Show in lecture".
  // Shares match correct / top_wrong_share in MOCK.insights. TODO(real): counted from attempts.
  const distribution = {
    1036: [["[1, 2]", 0.38], ["[1, 2, 3]", 0.51], ["[3]", 0.03], ["[1, 2, [3]]", 0.08]],
    1016: [["True", 0.54], ["False", 0.41], ["No answer (skipped)", 0.05]],
    1021: [["6", 0.34], ["None", 0.6], ["3", 0.02], ["An error", 0.04]],
    1025: [["0 2 4", 0.63], ["2 4 6", 0.31], ["0 2 4 6", 0.04], ["Other", 0.02]],
    1043: [["1", 0.01], ["2", 0.04], ["3", 0.66], ["4", 0.29]],
  };

  // ---- G7: how many attempts / students each reported question touches. ----------------------
  // TODO(real): counted from attempts on the question in the class's frozen set.
  const question_reach = {
    1001: { attempts: 31, students: 17, sets: ["Midterm practice"], trailing_space_attempts: 9, trailing_space_students: 6 },
    1030: { attempts: 26, students: 15, sets: ["Midterm practice"] },
    1021: { attempts: 47, students: 22, sets: ["Midterm practice"] },
    1043: { attempts: 44, students: 21, sets: ["Midterm practice"] },
    1059: { attempts: 12, students: 9, sets: ["Midterm practice"] },
  };

  // ---- F3s: 30-second refresher after a wrong answer, keyed by subtopic of the 6 queued questions.
  // TODO(real): generated with the question from the course book and reviewed by the professor
  // (see frontend/src/app/experiments/tutorials-inline). Outputs checked by running the code.
  const refreshers = {
    "Aliasing": {
      title: "Assignment doesn't copy a list",
      lines: ["b = a gives the same list a second name; there is still only one list.", "A change made through either name shows up through both.", "To get a separate list, copy it: b = a[:] or b = list(a)."],
      code: "a = [1, 2]\nb = a\nb.append(3)\nprint(a)", output: "[1, 2, 3]",
    },
    "range() and counted loops": {
      title: "range() stops before the stop value",
      lines: ["range(start, stop, step) begins at start and adds step each time.", "It never produces stop itself.", "range(3) is 0, 1, 2: it starts at 0 when you give only one number."],
      code: "for i in range(2, 9, 3):\n    print(i, end=' ')", output: "2 5 8",
    },
    "Loop accumulators": {
      title: "Set up before, update inside, use after",
      lines: ["An accumulator is created once, before the loop starts.", "Each pass through the loop updates it.", "The result is used after the loop, so return is not indented under for."],
      code: "total = 0\nfor n in [4, 5, 6]:\n    total += n\nprint(total)", output: "15",
    },
    "Keys and values": {
      title: "Keys must be immutable",
      lines: ["A dictionary finds a key by its hash, so the key can't change after it is stored.", "Strings, numbers and tuples can be keys; lists and dicts can't."],
      code: "d = {(1, 2): 'point'}\nprint(d[(1, 2)])", output: "point",
    },
    "Logical operators": {
      title: "and needs both sides True",
      lines: ["a and b is True only when both are True; a or b when at least one is.", "not flips True and False, and is applied before and and or."],
      code: "print(4 > 1 and not 2 > 3)", output: "True",
    },
    "Slicing": {
      title: "The stop index is left out",
      lines: ["s[start:stop] takes the characters from start up to, but not including, stop.", "So the slice has stop - start characters."],
      code: "s = 'python'\nprint(s[1:4], len(s[1:4]))", output: "yth 3",
    },
  };

  M.run = { by_section, distribution, question_reach, refreshers };
})();
