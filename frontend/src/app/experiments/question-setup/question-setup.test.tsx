/**
 * Plan logic, and a click-through of the wizard for each course: mining finishes, every style
 * gets a verdict, the summary lists the chosen ones, and the plan totals what is missing.
 */

import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BIOLOGY } from "./mock-biology";
import { PHYSICS } from "./mock-physics";
import { PYTHON } from "./mock-python";
import type { Domain } from "./mock-types";
import { buildPlan, type Decision, deckFor, FLOOR_PER_CELL, rulesFromSkips } from "./plan";
import { Wizard } from "./wizard";

const ALL = [PYTHON, PHYSICS, BIOLOGY];

function allApproved(domain: Domain) {
  return new Set(domain.templates.map((template) => template.id));
}

describe("mock data", () => {
  it.each(ALL)("$id: taxonomy counts match the header and every template uses an enabled type", (domain) => {
    const subtopics = domain.topics.reduce((sum, topic) => sum + topic.subtopics.length, 0);
    expect(domain.topics.length).toBe(domain.taxonomy.topics);
    expect(subtopics).toBe(domain.taxonomy.subtopics);
    for (const template of [...domain.templates, ...domain.reserve]) {
      expect(domain.questionTypes[template.questionType], template.id).toBeDefined();
    }
  });
});

describe("buildPlan", () => {
  it("fills every cell up to the floor when every style is approved", () => {
    const plan = buildPlan(PHYSICS, PHYSICS.templates, allApproved(PHYSICS), new Set());
    const expected = PHYSICS.topics
      .flatMap((topic) => topic.subtopics)
      .reduce(
        (sum, subtopic) =>
          sum + Object.values(subtopic.have).reduce((s, have) => s + Math.max(0, FLOOR_PER_CELL - have), 0),
        0,
      );
    expect(plan.totalAdd).toBe(expected);
    expect(plan.blockedCells).toBe(0);
    expect([...plan.byTemplate.values()].reduce((a, b) => a + b, 0)).toBe(plan.totalAdd);
  });

  it("blocks hard cells when no hard style is approved", () => {
    const noHard = new Set(PYTHON.templates.filter((t) => t.difficulty !== "hard").map((t) => t.id));
    const plan = buildPlan(PYTHON, PYTHON.templates, noHard, new Set());
    const subtopics = PYTHON.topics.reduce((sum, topic) => sum + topic.subtopics.length, 0);
    expect(plan.blockedCells).toBe(subtopics);
  });

  it("keeps code styles away from File I/O and leaves the rest of that cell to other styles", () => {
    const onlyCoding = new Set(["py-e-mcq", "py-m-trace", "py-h-code"]);
    const plan = buildPlan(PYTHON, PYTHON.templates, onlyCoding, new Set());
    const io = plan.topics.find((row) => row.topic.id === "io");
    expect(io?.subtopics.every((row) => row.cells.hard.blocked === "not-applicable")).toBe(true);
  });

  it("leaves excluded subtopics out of the totals", () => {
    const all = allApproved(BIOLOGY);
    const full = buildPlan(BIOLOGY, BIOLOGY.templates, all, new Set());
    const without = buildPlan(BIOLOGY, BIOLOGY.templates, all, new Set(["gen-2"]));
    expect(without.totalAdd).toBe(full.totalAdd - 9);
    expect(without.cellsTotal).toBe(full.cellsTotal - 3);
  });
});

describe("deck and rules", () => {
  it("drops true/false styles when the professor asks for fewer", () => {
    const deck = deckFor(PYTHON, new Set(["Fewer true / false"]));
    expect(deck.some((template) => template.questionType === "true_false")).toBe(false);
  });

  it("turns a skip with a reason into a rule and ignores a bare skip", () => {
    const decisions: Record<string, Decision> = {
      "py-e-tf": { verdict: "skipped", reason: "Too easy" },
      "py-e-mcq": { verdict: "skipped", reason: null },
    };
    const rules = rulesFromSkips(PYTHON.templates, decisions, PYTHON.questionTypes);
    expect(rules).toEqual(["True / false questions at easy level should need more than one step."]);
  });
});

describe("Wizard", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    window.scrollTo = vi.fn();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it.each(ALL)("$id: goes from mining to a plan", (domain) => {
    render(<Wizard domain={domain} />);
    const next = () => screen.getByRole("button", { name: /choose question styles|review my styles|see the plan/i });

    expect(next()).toBeDisabled();
    for (let i = 0; i < 6; i += 1) {
      act(() => {
        vi.advanceTimersByTime(900);
      });
    }
    expect(screen.getByText("Finished reading the book")).toBeInTheDocument();
    fireEvent.click(next());

    // Skip the first style with a reason, use every other one.
    fireEvent.click(screen.getByRole("button", { name: /^skip$/i }));
    fireEvent.click(screen.getByRole("button", { name: "Not this kind of question" }));
    for (let i = 1; i < domain.templates.length; i += 1) {
      fireEvent.click(screen.getByRole("button", { name: /use this style/i }));
    }
    expect(screen.getByText(`All ${domain.templates.length} styles reviewed`)).toBeInTheDocument();
    fireEvent.click(next());

    expect(screen.getByText(`${domain.templates.length - 1} styles the generator will use`)).toBeInTheDocument();
    expect(screen.getByText(/^Don't write /)).toBeInTheDocument();
    fireEvent.click(next());

    const generate = screen.getByRole("button", { name: /^generate \d+ questions$/i });
    fireEvent.click(generate);
    expect(screen.getByText("Prototype: nothing was generated.")).toBeInTheDocument();
  });
});
