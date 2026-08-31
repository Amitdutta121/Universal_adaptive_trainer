import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { CoverageReport } from "@/lib/api/types";
import { CoverageGrid } from "./coverage-grid";

beforeAll(() => {
  if (typeof ResizeObserver !== "undefined") return;

  class ResizeObserverMock {
    observe() {}
    unobserve() {}
    disconnect() {}
  }

  globalThis.ResizeObserver = ResizeObserverMock as typeof ResizeObserver;
});

const report: CoverageReport = {
  curriculum_version_id: 2,
  curriculum_label: "Python Programming Adaptive Training Taxonomy",
  set_version_id: null,
  minimum_per_cell: 3,
  question_count: 8,
  total_cells: 6,
  empty_cells: 2,
  thin_cells: 1,
  ready_cells: 3,
  gap_count: 3,
  questions_needed: 6,
  is_servable: false,
  is_ready: false,
  topics: [
    {
      topic_id: 0,
      topic_name: "Basics",
      approved_questions: 1,
      subtopics: [
        {
          subtopic_id: 10,
          subtopic_name: "Variables",
          topic_id: 0,
          topic_name: "Basics",
          cells: [
            { difficulty: "easy", count: 1, state: "thin", needed: 2 },
            { difficulty: "medium", count: 0, state: "empty", needed: 3 },
            { difficulty: "hard", count: 0, state: "empty", needed: 3 },
          ],
        },
      ],
    },
    {
      topic_id: 1,
      topic_name: "Functions",
      approved_questions: 8,
      subtopics: [
        {
          subtopic_id: 11,
          subtopic_name: "Return values",
          topic_id: 1,
          topic_name: "Functions",
          cells: [
            { difficulty: "easy", count: 3, state: "ready", needed: 0 },
            { difficulty: "medium", count: 2, state: "thin", needed: 1 },
            { difficulty: "hard", count: 0, state: "empty", needed: 3 },
          ],
        },
        {
          subtopic_id: 12,
          subtopic_name: "Variable scope",
          topic_id: 1,
          topic_name: "Functions",
          cells: [
            { difficulty: "easy", count: 3, state: "ready", needed: 0 },
            { difficulty: "medium", count: 0, state: "empty", needed: 3 },
            { difficulty: "hard", count: 0, state: "empty", needed: 3 },
          ],
        },
      ],
    },
  ],
  subtopics: [],
};

describe("CoverageGrid", () => {
  it("renders one card per topic and explains subtopic coverage on hover", async () => {
    const user = userEvent.setup();

    render(
      <TooltipProvider>
        <CoverageGrid report={report} />
      </TooltipProvider>,
    );

    expect(screen.getByText("Topic coverage map")).toBeInTheDocument();
    expect(screen.getByText("1 square = 1 subtopic")).toBeInTheDocument();
    expect(screen.getByText("Lower volume")).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 3 }).map((node) => node.textContent)).toEqual([
      "Basics",
      "Functions",
    ]);
    expect(screen.getByText("1/3")).toBeInTheDocument();
    expect(screen.getByText("8/6")).toBeInTheDocument();
    expect(screen.getByText("Functions")).toBeInTheDocument();
    expect(screen.getByText("2/2 subtopics")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Generate questions for Basics" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Generate questions for Functions" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Return values")).not.toBeInTheDocument();

    await user.hover(
      screen.getByRole("button", { name: "Return values subtopic coverage in Functions" }),
    );

    expect(await screen.findByText("Return values")).toBeInTheDocument();
    expect(screen.getByText("5 questions in this subtopic")).toBeInTheDocument();
    expect(screen.getByText("2 of 3 difficulty levels covered")).toBeInTheDocument();
    expect(screen.getByText("Moderate question volume in this topic")).toBeInTheDocument();
    expect(screen.getByText("Topic total: 8/6 questions")).toBeInTheDocument();
  });
});
