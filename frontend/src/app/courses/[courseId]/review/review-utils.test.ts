import { describe, expect, it } from "vitest";
import { presentTests } from "./review-utils";

describe("presentTests", () => {
  it("reads the row's JSON tests, whose entries carry `assert`", () => {
    const stored = JSON.stringify([
      { stdin: "", stdout: null, assert: "assert f(1) == 2" },
      { stdin: "", stdout: null, assert: "assert f(2) == 3" },
    ]);
    expect(presentTests(stored)).toEqual([
      { stdin: "", stdout: null, assert: "assert f(1) == 2" },
      { stdin: "", stdout: null, assert: "assert f(2) == 3" },
    ]);
  });

  it("reads generated content tests, whose entries carry `assert_code`", () => {
    expect(
      presentTests([
        { stdin: "", stdout: null, assert_code: "abs(g(4) - 2) < 0.001" },
        { stdin: "3\n", stdout: "6\n", assert_code: null },
      ]),
    ).toEqual([
      { stdin: "", stdout: null, assert: "abs(g(4) - 2) < 0.001" },
      { stdin: "3\n", stdout: "6\n", assert: null },
    ]);
  });

  it("returns null when nothing is checkable", () => {
    expect(presentTests(null)).toBeNull();
    expect(presentTests("not json")).toBeNull();
    expect(presentTests([{ stdin: "x", stdout: null }])).toBeNull();
  });
});
