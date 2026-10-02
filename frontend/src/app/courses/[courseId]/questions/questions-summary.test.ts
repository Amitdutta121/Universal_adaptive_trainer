import { describe, expect, it } from "vitest";
import { questionsSummary, subjectLabel } from "./questions-summary";

const subjects = [
  { id: "intro_python", label: "Intro programming (Python)" },
  { id: "physics", label: "Physics" },
  { id: "custom", label: "Something else" },
];

describe("subjectLabel", () => {
  it("names the course's subject preset", () => {
    expect(subjectLabel("physics", subjects)).toBe("Physics");
  });

  it("names nothing for a custom subject, an unknown one, or before data loads", () => {
    expect(subjectLabel("custom", subjects)).toBeNull();
    expect(subjectLabel("chemistry", subjects)).toBeNull();
    expect(subjectLabel(undefined, subjects)).toBeNull();
    expect(subjectLabel("physics", undefined)).toBeNull();
  });
});

describe("questionsSummary", () => {
  it("uses the subject label when there is one", () => {
    expect(questionsSummary("Biology")).toBe(
      "Generate, validate and review assessment questions for Biology.",
    );
  });

  it("falls back to neutral wording", () => {
    expect(questionsSummary(null)).toBe("Generate, validate and review assessment questions.");
  });
});
