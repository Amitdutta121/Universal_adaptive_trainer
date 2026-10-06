import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { CoverageReport, GenerationRunResponse, Job } from "@/lib/api/types";

// Links inside a course are built from the URL's course id (`lib/course.ts`).
vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof import("next/navigation")>()),
  useParams: () => ({ courseId: "7" }),
}));

const mutate = vi.fn();
const useGenerateCoverageRun = vi.fn(() => ({
  mutate,
  isPending: false,
  isSuccess: false,
  data: undefined as { job_id: string } | undefined,
  error: null as unknown,
}));
// The run is a background job; the button follows it through the Jobs list.
const useJob = vi.fn((_jobId: string | undefined): Job | undefined => undefined);

vi.mock("@/lib/api/queries", () => ({
  useGenerateCoverageRun: () => useGenerateCoverageRun(),
  useJob: (jobId: string | undefined) => useJob(jobId),
}));

/** A coverage-fill job of the Jobs list, as `GET /api/jobs` reports it. */
function coverageJob(overrides: Partial<Job>): Job {
  return {
    id: "job-1",
    kind: "coverage_fill",
    title: "Fill 2 coverage gaps",
    status: "running",
    done: 1,
    total: 2,
    counts: {},
    error: null,
    link: null,
    result: null,
    can_cancel: false,
    cancel_requested: false,
    retry_label: null,
    created_at: "2026-10-06T12:00:00",
    started_at: "2026-10-06T12:00:01",
    finished_at: null,
    ...overrides,
  };
}

import { CoverageGrid } from "./coverage-grid";

beforeEach(() => {
  mutate.mockClear();
  useGenerateCoverageRun.mockReset();
  useGenerateCoverageRun.mockReturnValue({
    mutate,
    isPending: false,
    isSuccess: false,
    data: undefined,
    error: null,
  });
  useJob.mockReset();
  useJob.mockReturnValue(undefined);
});

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

const oneTopicReport: CoverageReport = {
  ...report,
  topics: [report.topics[0]],
};

const completeReport: CoverageReport = {
  ...report,
  topics: [
    {
      topic_id: 2,
      topic_name: "Loops",
      approved_questions: 9,
      subtopics: [
        {
          subtopic_id: 20,
          subtopic_name: "For loops",
          topic_id: 2,
          topic_name: "Loops",
          cells: [
            { difficulty: "easy", count: 3, state: "ready", needed: 0 },
            { difficulty: "medium", count: 3, state: "ready", needed: 0 },
            { difficulty: "hard", count: 3, state: "ready", needed: 0 },
          ],
        },
      ],
    },
  ],
};

describe("CoverageGrid Generate button", () => {
  it("fires the mutation with the topic's gap targets on click", async () => {
    const user = userEvent.setup();
    render(
      <TooltipProvider>
        <CoverageGrid report={oneTopicReport} />
      </TooltipProvider>,
    );

    await user.click(screen.getByRole("button", { name: "Generate questions for Basics" }));

    expect(mutate).toHaveBeenCalledWith({
      targets: [
        { subtopic_id: 10, difficulty: "easy" },
        { subtopic_id: 10, difficulty: "medium" },
        { subtopic_id: 10, difficulty: "hard" },
      ],
    });
  });

  it("disables Generate entirely for a topic with zero gaps", () => {
    render(
      <TooltipProvider>
        <CoverageGrid report={completeReport} />
      </TooltipProvider>,
    );

    expect(screen.getByRole("button", { name: "Generate questions for Loops" })).toBeDisabled();
  });

  it("shows a spinner and disables the button while the run is in flight", () => {
    useGenerateCoverageRun.mockReturnValue({
      mutate,
      isPending: true,
      isSuccess: false,
      data: undefined,
      error: null,
    });

    render(
      <TooltipProvider>
        <CoverageGrid report={oneTopicReport} />
      </TooltipProvider>,
    );

    const button = screen.getByRole("button", { name: "Generate questions for Basics" });
    expect(button).toBeDisabled();
    expect(screen.getByText("Generating…")).toBeInTheDocument();
  });

  it("renders the run summary and a Review link filtered by run_id on success", () => {
    const run: GenerationRunResponse = {
      run_id: "run_abc123",
      generated: [
        {
          question_id: 1,
          requested_subtopic_id: 10,
          requested_difficulty: "easy",
          claimed_topic_id: 0,
          claimed_subtopic_ids: [10],
          section_id: 5,
          status: "validation_passed",
          aim_matched: true,
        },
        {
          question_id: 2,
          requested_subtopic_id: 10,
          requested_difficulty: "medium",
          claimed_topic_id: 3,
          claimed_subtopic_ids: [30],
          section_id: 6,
          status: "validation_passed",
          aim_matched: false,
        },
      ],
      skipped: [],
      failed: [],
      possible_duplicates: 1,
    };
    useGenerateCoverageRun.mockReturnValue({
      mutate,
      isPending: false,
      isSuccess: true,
      data: { job_id: "job-1" },
      error: null,
    });
    useJob.mockReturnValue(coverageJob({ status: "done", done: 2, result: run }));

    render(
      <TooltipProvider>
        <CoverageGrid report={oneTopicReport} />
      </TooltipProvider>,
    );

    expect(
      screen.getByText("2 generated · 1 possible duplicate · 1 on a different topic"),
    ).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "Review these →" });
    expect(link).toHaveAttribute("href", "/courses/7/questions?run_id=run_abc123");
  });

  it("shows Generating and stays disabled when the server reports the topic active, even with no local mutation", () => {
    // Simulates a reload or nav-back mid-run: this hook instance never fired
    // the mutation (isPending/data/error all empty), but the server still
    // reports the topic as generating.
    render(
      <TooltipProvider>
        <CoverageGrid report={{ ...oneTopicReport, active_run_topic_ids: [0] }} />
      </TooltipProvider>,
    );

    const button = screen.getByRole("button", { name: "Generate questions for Basics" });
    expect(button).toBeDisabled();
    expect(screen.getByText("Generating…")).toBeInTheDocument();
    expect(mutate).not.toHaveBeenCalled();
  });

  it("does not mark a topic generating just because a different topic's run is active", () => {
    render(
      <TooltipProvider>
        <CoverageGrid report={{ ...report, active_run_topic_ids: [1] }} />
      </TooltipProvider>,
    );

    expect(
      screen.getByRole("button", { name: "Generate questions for Basics" }),
    ).not.toBeDisabled();
    expect(screen.getByRole("button", { name: "Generate questions for Functions" })).toBeDisabled();
    expect(screen.getByText("Generating…")).toBeInTheDocument();
  });

  it("keeps showing Generating while its queued job is still running", () => {
    useGenerateCoverageRun.mockReturnValue({
      mutate,
      isPending: false,
      isSuccess: true,
      data: { job_id: "job-1" },
      error: null,
    });
    useJob.mockReturnValue(coverageJob({ status: "running" }));

    render(
      <TooltipProvider>
        <CoverageGrid report={oneTopicReport} />
      </TooltipProvider>,
    );

    expect(screen.getByRole("button", { name: "Generate questions for Basics" })).toBeDisabled();
    expect(screen.getByText("Generating…")).toBeInTheDocument();
    expect(useJob).toHaveBeenCalledWith("job-1");
  });

  it("says why its job failed", () => {
    useGenerateCoverageRun.mockReturnValue({
      mutate,
      isPending: false,
      isSuccess: true,
      data: { job_id: "job-1" },
      error: null,
    });
    useJob.mockReturnValue(
      coverageJob({ status: "failed", error: "Interrupted by a server restart." }),
    );

    render(
      <TooltipProvider>
        <CoverageGrid report={oneTopicReport} />
      </TooltipProvider>,
    );

    expect(screen.getByText("Interrupted by a server restart.")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Generate questions for Basics" }),
    ).not.toBeDisabled();
  });

  it("shows a readable error instead of a silent no-op", () => {
    useGenerateCoverageRun.mockReturnValue({
      mutate,
      isPending: false,
      isSuccess: false,
      data: undefined,
      error: {
        status: 502,
        code: "upstream_unreachable",
        message: "The model provider could not be reached.",
      },
    });

    render(
      <TooltipProvider>
        <CoverageGrid report={oneTopicReport} />
      </TooltipProvider>,
    );

    expect(screen.getByText("The model provider could not be reached")).toBeInTheDocument();
  });
});
