import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { JudgesScreen } from "./judges-screen";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/app/courses/[courseId]/questions/setup/custom-rules", () => ({
  CustomRules: () => null,
}));

const prompt = (metric: "difficulty" | "subtopic") => ({
  metric,
  label: metric,
  system_prompt: `${metric} prompt text`,
  shipped_prompt: "p",
  edited: false,
  learned: false,
  rules: [],
  evidence_count: 0,
  available_disagreements: 3,
  revision: 0,
  note: null,
  updated_at: null,
});

const trustWindow = (observations: number, agreements: number, trusted = false) => ({
  observations,
  agreements,
  agreement_rate: observations ? agreements / observations : 0,
  trusted,
  audit_revoked: false,
});

let paused = false;

const confirmGuideline = vi.fn();
const deleteGuideline = vi.fn();
const guideline = (id: number, text: string, status: "pending" | "active", support: number) => ({
  id,
  target: "generator:multiple_choice",
  question_type: "multiple_choice",
  text,
  status,
  support_count: support,
  review_ids: Array.from({ length: support }, (_, i) => i + 1),
  confirmed_by_professor: false,
  created_at: "2026-10-08T00:00:00Z",
  updated_at: null,
});

const scorecardRow = (
  metric: "issues" | "difficulty" | "subtopic",
  extras: Record<string, number | null> = {},
) => ({
  metric,
  n: 20,
  agreements: 18,
  agreement: 0.9,
  kappa: 0.6,
  agreement_low: 0.699,
  agreement_high: 0.972,
  missed: 1,
  false_alarms: 1,
  flags: 2,
  flag_rate: 0.1,
  retries: 0,
  drops: 0,
  ...extras,
});

vi.mock("@/lib/api/queries", () => ({
  useApprovedCurriculum: () => ({ isPending: false, data: { version: { id: 5 } } }),
  useJudgePrompts: () => ({
    isPending: false,
    error: null,
    data: {
      prompts: [prompt("difficulty"), prompt("subtopic")],
      rubric_version: "r",
      shipped_rubric_version: "r",
    },
  }),
  useJudgeScorecard: () => ({
    isPending: false,
    error: null,
    data: {
      judges: [
        scorecardRow("issues", { false_alarms: 4, missed: 2, retries: 0, drops: 0 }),
        scorecardRow("difficulty", { retries: 3, drops: 1 }),
        scorecardRow("subtopic", { n: 0, agreements: 0, agreement: null, kappa: null }),
      ],
    },
  }),
  useJudgeStats: () => ({
    data: {
      rubric_version: "r",
      judges: [
        {
          metric: "difficulty",
          observations: 20,
          agreements: 18,
          agreement_rate: 0.9,
          learnable_disagreements: 3,
          disagreements_needed: 5,
        },
        {
          metric: "subtopic",
          observations: 0,
          agreements: 0,
          agreement_rate: null,
          learnable_disagreements: 0,
          disagreements_needed: 5,
        },
      ],
      styles: [
        {
          curriculum_version_id: 5,
          style_id: "py.trace_output",
          style_name: "Predict the output",
          trusted: paused,
          metrics: {
            difficulty: trustWindow(20, 18, paused),
            subtopic: trustWindow(20, 20, paused),
            acceptance: trustWindow(12, 12),
          },
        },
      ],
      held_out_pairs: 2,
      held_out_needed: 5,
      learning_enabled: true,
      learning_paused: paused,
      trusted_style_count: paused ? 1 : 0,
      min_observations: 20,
      min_agreement: 0.9,
      min_acceptance: 0.9,
    },
  }),
  useGuidelines: () => ({
    isPending: false,
    error: null,
    data: {
      active_support: 2,
      guidelines: [
        guideline(11, "Put a short code block in the stem.", "active", 2),
        guideline(12, "Ask the question directly.", "pending", 1),
      ],
    },
  }),
  useConfirmGuideline: () => ({ mutateAsync: confirmGuideline, isPending: false }),
  useDeleteGuideline: () => ({ mutateAsync: deleteGuideline, isPending: false }),
  useRevertJudgePrompt: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useSaveJudgePrompt: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

describe("Judge scorecard", () => {
  it("shows agreement with a 95% range, kappa, false alarms, retries and drops", () => {
    render(<JudgesScreen />);
    expect(screen.getByText("How each judge is doing")).toBeInTheDocument();
    const issues = screen.getByText("Issues").closest("tr");
    const difficulty = screen.getAllByText("Difficulty")[0].closest("tr");
    expect(issues).toHaveTextContent("18/20 (90%)");
    expect(issues).toHaveTextContent("70%–97%");
    expect(issues).toHaveTextContent("0.60");
    expect(issues).toHaveTextContent("4");
    expect(difficulty).toHaveTextContent("3");
    expect(difficulty).toHaveTextContent("1");
  });
});

describe("JudgesScreen stats", () => {
  it("shows professor agreement and rewrite progress per judge", () => {
    paused = false;
    render(<JudgesScreen />);
    expect(screen.getByText("90%")).toBeInTheDocument();
    expect(screen.getByText("18/20 agreed")).toBeInTheDocument();
    expect(screen.getByText("No reviewed questions under this prompt yet")).toBeInTheDocument();
    expect(screen.getAllByText("Next rewrite: 3 of 5 disagreements")[0]).toBeInTheDocument();
  });

  it("keeps the prompt behind More", async () => {
    paused = false;
    render(<JudgesScreen />);
    expect(screen.queryByText("difficulty prompt text")).not.toBeInTheDocument();
    expect(screen.queryByText(/rubric version/i)).not.toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: "More" })[0]);
    expect(screen.getByText("difficulty prompt text")).toBeInTheDocument();
    expect(screen.queryByText("subtopic prompt text")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Less" })).toBeInTheDocument();
  });

  it("lists trust per style with what is still missing", () => {
    paused = false;
    render(<JudgesScreen />);
    expect(screen.getByText("Predict the output")).toBeInTheDocument();
    expect(screen.getByText("Building trust: 12 of 20 reviews")).toBeInTheDocument();
  });

  it("says when rewrites are paused", () => {
    paused = true;
    render(<JudgesScreen />);
    expect(
      screen.getAllByText("Rewrites paused while 1 style skips review")[0],
    ).toBeInTheDocument();
    expect(screen.getByText("Skips review")).toBeInTheDocument();
  });

  it("warns in the editor that saving resets trust", async () => {
    paused = true;
    render(<JudgesScreen />);
    await userEvent.click(screen.getAllByRole("button", { name: "Edit prompt" })[0]);
    expect(await screen.findByText(/Saving resets trust: 1 style goes back/)).toBeInTheDocument();
  });
});

describe("Generator guidelines", () => {
  it("lists pending and active guidelines with their support", () => {
    render(<JudgesScreen />);
    const active = screen.getByText("Put a short code block in the stem.").closest("tr");
    const pending = screen.getByText("Ask the question directly.").closest("tr");
    expect(active).toHaveTextContent("2/2");
    expect(active).toHaveTextContent("active");
    expect(pending).toHaveTextContent("1/2");
    expect(pending).toHaveTextContent("pending");
    // Only a pending guideline can be confirmed; both can be deleted.
    expect(screen.getAllByRole("button", { name: "Confirm" })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "Delete" })).toHaveLength(2);
  });

  it("confirms and deletes by id", async () => {
    render(<JudgesScreen />);
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(confirmGuideline).toHaveBeenCalledWith(12);
    await userEvent.click(screen.getAllByRole("button", { name: "Delete" })[0]);
    expect(deleteGuideline).toHaveBeenCalledWith(11);
  });
});
