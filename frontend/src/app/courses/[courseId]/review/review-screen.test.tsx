import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { toast } from "sonner";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { JudgeRail } from "./components/review-feedback";
import { ReviewScreen } from "./review-screen";
import type { QuestionDetail } from "./review-types";

// URL state is not under test; keep it as plain component state.
vi.mock("nuqs", () => {
  const parser = { withDefault: (value: unknown) => ({ defaultValue: value }) };
  return {
    parseAsInteger: {},
    parseAsStringLiteral: () => parser,
    useQueryState: (_key: string, options?: { defaultValue?: unknown }) =>
      useState(options?.defaultValue ?? null),
  };
});
vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));
const { invalidateQueries } = vi.hoisted(() => ({ invalidateQueries: vi.fn() }));
vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries }),
}));
vi.mock("@/components/page-header", () => ({
  PageHeader: ({ title, actions }: { title: string; actions?: React.ReactNode }) => (
    <header>
      <h1>{title}</h1>
      {actions}
    </header>
  ),
}));
vi.mock("@/components/course-link", () => ({
  CourseLink: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
// The question body renderers need a full per-type payload; this test is about the verdict.
vi.mock("./components/review-question-content", () => ({
  ReviewQuestionSurface: () => null,
  ReviewQuestionContent: () => null,
}));

const submitReview = vi.fn();
const startNextRound = vi.fn();
let currentSetup: {
  setup: { id: number; latest_round: { id: number; status: string } | null } | null;
} = { setup: null };
let roundData: unknown;
let submitPending = false;

function makeDetail(): QuestionDetail {
  return {
    question: {
      id: 42,
      prompt: "What does print(1 + 1) output?",
      question_type: "output_prediction",
      kind: "discrete",
      difficulty: "easy",
      subtopic_ids: [1],
    },
    reference_solution: null,
    tests: null,
    content: null,
    taxonomy: { curriculum: "Python", topic: "Basics", subtopics: ["Variables"] },
    validation_passed: true,
    validation_checks: [{ name: "answer_matches", passed: true }],
    pedagogical_eval: {
      status: "completed",
      gate: "needs_review",
      metrics: [
        { metric: "issues", passed: false, issue_codes: ["ambiguous"] },
        { metric: "generatability", passed: true },
        { metric: "difficulty", passed: false, proposed_difficulty: "hard" },
        { metric: "subtopic", passed: true, proposed_subtopic_ids: [2] },
      ],
    },
    custom_results: [
      { judge_id: 1, rule_text: "No global variables", kind: "llm", passed: true },
      { judge_id: 2, rule_text: "Uses f-strings", kind: "pattern", passed: false },
    ],
  } as unknown as QuestionDetail;
}

let detail: QuestionDetail | null;
let remaining: number;

vi.mock("@/lib/api/queries", () => ({
  qk: { setup: { all: ["setup"] } },
  useApprovedCurriculum: () => ({
    data: {
      version: { id: 5 },
      topics: [
        {
          name: "Basics",
          subtopics: [
            { id: 1, name: "Variables" },
            { id: 2, name: "Printing" },
          ],
        },
      ],
    },
  }),
  useReviewQueue: () => ({
    data: { question: detail, reviewed: 3 - remaining, total: 3, remaining, mode: "all" },
    isPending: false,
    isError: false,
    error: null,
  }),
  useSubmitReview: () => ({ mutateAsync: submitReview, isPending: submitPending }),
  useCurrentSetup: () => ({ data: currentSetup, isError: false, error: null }),
  useStartNextRound: () => ({ mutateAsync: startNextRound, isPending: false }),
  useRound: (roundId: number | null) => ({
    data: roundId == null ? undefined : roundData,
    isError: false,
    error: null,
  }),
}));

beforeEach(() => {
  detail = makeDetail();
  remaining = 3;
  invalidateQueries.mockReset();
  currentSetup = { setup: null };
  roundData = undefined;
  submitPending = false;
  vi.mocked(toast.error).mockReset();
  submitReview.mockReset().mockResolvedValue({ outcome: null });
  startNextRound.mockReset().mockResolvedValue({ round_id: 9 });
});

describe("JudgeRail", () => {
  it("shows only the answer check, difficulty, topic and custom rules", () => {
    render(<JudgeRail detail={makeDetail()} subtopicNames={new Map([[2, "Printing"]])} />);
    const rows = screen.getAllByTestId("judge-row");
    expect(rows.map((row) => row.querySelector("p")?.textContent)).toEqual([
      "Answer check",
      "Difficulty",
      "Topic",
      "No global variables",
      "Uses f-strings",
    ]);
    expect(screen.queryByText("Issues")).not.toBeInTheDocument();
    expect(screen.queryByText("Generatability")).not.toBeInTheDocument();
    expect(screen.getByText("Judge says Hard")).toBeInTheDocument();
    expect(screen.getByText("Judge says Printing")).toBeInTheDocument();
  });
});

describe("ReviewScreen verdict", () => {
  it("requires explicit confirmation even when both judge presets look correct", async () => {
    const user = userEvent.setup();
    render(<ReviewScreen />);
    const submit = screen.getByRole("button", { name: /Accept and continue/ });
    expect(submit).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Confirm difficulty" }));
    expect(submit).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Confirm subtopics" }));
    await user.click(submit);
    expect(submitReview).toHaveBeenCalledWith({
      questionId: 42,
      body: { decision: "approve", corrected_difficulty: "hard", corrected_subtopic_ids: [2] },
    });
  });
  it("presets the judge's difficulty and subtopics and sends the corrected values", async () => {
    const user = userEvent.setup();
    render(<ReviewScreen />);

    const difficulty = screen.getByRole("radiogroup", { name: "Difficulty" });
    expect(within(difficulty).getByRole("radio", { name: "Hard" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(screen.getByRole("button", { name: "Subtopics" })).toHaveTextContent("Printing");

    await user.click(within(difficulty).getByRole("radio", { name: "Medium" }));
    await user.click(screen.getByRole("button", { name: "Confirm subtopics" }));
    await user.click(screen.getByRole("button", { name: /Accept and continue/ }));

    expect(submitReview).toHaveBeenCalledWith({
      questionId: 42,
      body: {
        decision: "approve",
        corrected_difficulty: "medium",
        corrected_subtopic_ids: [2],
      },
    });
  });

  it("rejects without any reason, with an optional one-line comment", async () => {
    const user = userEvent.setup();
    render(<ReviewScreen />);

    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reject" }));
    const submit = screen.getByRole("button", { name: /Reject and continue/ });
    expect(submit).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Confirm difficulty" }));
    await user.click(screen.getByRole("button", { name: "Confirm subtopics" }));
    expect(submit).toBeEnabled();
    await user.type(screen.getByRole("textbox", { name: "Comment" }), "Off topic");
    await user.click(submit);

    expect(submitReview).toHaveBeenCalledWith({
      questionId: 42,
      body: {
        decision: "reject",
        comment: "Off topic",
        corrected_difficulty: "hard",
        corrected_subtopic_ids: [2],
      },
    });
    expect(submitReview.mock.calls[0][0].body).not.toHaveProperty("reasons");
  });

  it("keeps Skip enabled while a review saves", () => {
    submitPending = true;
    render(<ReviewScreen />);
    expect(screen.getByRole("button", { name: /Saving/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Skip/ })).toBeEnabled();
  });

  it("does not claim a refresh happened when the review is saved", async () => {
    submitReview.mockResolvedValue({
      outcome: {
        cell: "confirmed_bad",
        action: "This type's instruction is relearned from your reviews next round.",
        attributed_labels: [],
        refresh_error: "stale error",
      },
    });
    const user = userEvent.setup();
    render(<ReviewScreen />);
    await user.click(screen.getByRole("button", { name: "Reject" }));
    await user.click(screen.getByRole("button", { name: "Confirm difficulty" }));
    await user.click(screen.getByRole("button", { name: "Confirm subtopics" }));
    await user.click(screen.getByRole("button", { name: /Reject and continue/ }));

    expect(toast.error).toHaveBeenCalledWith("confirmed bad", {
      description: "This type's instruction is relearned from your reviews next round.",
    });
  });

  it("keeps Edit as a secondary action", async () => {
    const user = userEvent.setup();
    render(<ReviewScreen />);
    await user.click(screen.getByRole("button", { name: /Edit question/ }));
    expect(screen.getByRole("button", { name: /Save edit and accept/ })).toBeDisabled();
  });
});

describe("Generate next round", () => {
  it("is disabled with a hint when the taxonomy has no setup", () => {
    render(<ReviewScreen />);
    const button = screen.getByRole("button", { name: /Generate next round/ });
    expect(button).toBeDisabled();
    expect(button.parentElement).toHaveAttribute(
      "title",
      "Set up questions on the Questions page first.",
    );
  });

  it("starts the next round of the current setup", async () => {
    currentSetup = { setup: { id: 7, latest_round: null } };
    const user = userEvent.setup();
    render(<ReviewScreen />);

    const button = screen.getByRole("button", { name: /Generate next round/ });
    expect(button).toBeEnabled();
    await user.click(button);

    expect(startNextRound).toHaveBeenCalledWith({ setup_id: 7, size: 10 });
  });

  it("shows the progress of a round that is still generating", () => {
    currentSetup = { setup: { id: 7, latest_round: { id: 3, status: "running" } } };
    roundData = {
      id: 3,
      number: 2,
      status: "running",
      requested: 10,
      produced: 4,
      dropped: 1,
      error: null,
    };
    render(<ReviewScreen />);

    expect(screen.getByTestId("round-progress")).toHaveTextContent(
      "Generating round 2: produced 4, dropped 1 of 10",
    );
    expect(screen.getByRole("button", { name: /Generate next round/ })).toBeDisabled();
  });

  it("says how many reviews the round learned from, or why it could not", () => {
    currentSetup = { setup: { id: 7, latest_round: { id: 3, status: "running" } } };
    roundData = {
      id: 3,
      number: 2,
      status: "running",
      requested: 10,
      produced: 0,
      dropped: 0,
      lessons_applied: 3,
      lessons_error: null,
      error: null,
    };
    const { rerender } = render(<ReviewScreen />);
    expect(screen.getByTestId("round-progress")).toHaveTextContent(
      "Applied lessons from 3 reviews.",
    );

    roundData = { ...(roundData as object), lessons_applied: 0, lessons_error: "provider down" };
    rerender(<ReviewScreen />);
    expect(screen.getByTestId("round-progress")).toHaveTextContent(
      "Some lessons were not applied: provider down",
    );
  });
});

describe("Questions arriving during a round", () => {
  const running = (produced: number) => ({
    id: 3,
    number: 1,
    status: "running",
    requested: 10,
    produced,
    dropped: 0,
    error: null,
  });

  beforeEach(() => {
    currentSetup = { setup: { id: 7, latest_round: { id: 3, status: "running" } } };
  });

  it("says the next question is generating instead of that nothing is left", () => {
    detail = null;
    remaining = 0;
    roundData = running(0);
    render(<ReviewScreen />);

    expect(screen.getByTestId("next-question-generating")).toHaveTextContent(
      "Generating the next question",
    );
    expect(screen.queryByText("Nothing left to review")).not.toBeInTheDocument();
  });

  it("refetches the queue as each question lands, not only when the round ends", () => {
    roundData = running(0);
    const { rerender } = render(<ReviewScreen />);
    expect(invalidateQueries).not.toHaveBeenCalled();

    roundData = running(1);
    rerender(<ReviewScreen />);
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["questions", "review-queue"] });

    invalidateQueries.mockClear();
    roundData = running(2);
    rerender(<ReviewScreen />);
    expect(invalidateQueries).toHaveBeenCalledTimes(1);
  });

  it("is back to the normal empty state once the round is done", () => {
    detail = null;
    remaining = 0;
    roundData = { ...running(10), status: "done" };
    render(<ReviewScreen />);

    expect(screen.getByText("Nothing left to review")).toBeInTheDocument();
  });
});
