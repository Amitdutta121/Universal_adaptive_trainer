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
  system_prompt: "p",
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
  useRevertJudgePrompt: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useSaveJudgePrompt: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

describe("JudgesScreen stats", () => {
  it("shows professor agreement and rewrite progress per judge", () => {
    paused = false;
    render(<JudgesScreen />);
    expect(screen.getByText("18/20 agreed (90%)")).toBeInTheDocument();
    expect(screen.getByText("No reviewed questions under this prompt yet")).toBeInTheDocument();
    expect(screen.getAllByText("Next rewrite: 3 of 5 disagreements")[0]).toBeInTheDocument();
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
