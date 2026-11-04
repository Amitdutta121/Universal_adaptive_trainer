import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import type { AnsweredOut, ServedQuestionOut } from "@/lib/api/types";

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof import("next/navigation")>()),
  useRouter: () => ({ push: vi.fn() }),
}));

function block(id: number, markdown: string) {
  return {
    id,
    recipe_id: "py.misconception_line",
    guidance_level: "worked" as const,
    renderer: "markdown" as const,
    payload: { markdown },
  };
}

const served = {
  attempt_id: 11,
  ordinal: 1,
  served_difficulty: "easy",
  question_type: null,
  prompt: "What does print(2 + 3) show?",
  code: null,
  subtopic_name: "Using the REPL",
  resumed: false,
  live: false,
  preteach_blocks: [block(1, "Pre-teaching text")],
} as unknown as ServedQuestionOut;

const answered = {
  attempt_id: 11,
  training_session_id: 5,
  score: 0,
  detail: null,
  total_tests: null,
  passed_tests: null,
  mastery_before: null,
  mastery_after: null,
  tutorial_blocks: [block(2, "Worked tutorial text")],
} as unknown as AnsweredOut;

let session: { ended_at: string | null };
let next: { data: ServedQuestionOut | undefined; error: unknown; isError: boolean };
const mutateAsync = vi.fn(async () => answered);

vi.mock("@/lib/api/queries", () => ({
  useTrainingSession: () => ({
    isPending: false,
    isError: false,
    data: {
      id: 5,
      created_at: "2026-10-24T10:00:00",
      student_name: "Ada",
      answered_count: 0,
      served_count: 1,
      set_label: "CS189",
      set_version_id: 6,
      ...session,
    },
  }),
  useTrainingSessionProgress: () => ({ data: undefined }),
  useNextQuestion: () => ({ ...next, isPending: false, isFetching: false, refetch: vi.fn() }),
  useAttemptReview: () => ({ data: undefined }),
  useAnswerAttempt: () => ({ mutateAsync, isPending: false, isError: false, error: null }),
  useEndTrainingSession: () => ({ mutateAsync: vi.fn(), isPending: false, isError: false }),
  useRequestLiveQuestion: () => ({ mutate: vi.fn(), isPending: false }),
}));

import { StudentSessionScreen } from "./student-session-screen";

/** True when `first` comes before `second` in document (reading and focus) order. */
function precedes(first: HTMLElement, second: HTMLElement) {
  return Boolean(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING);
}

beforeEach(() => {
  session = { ended_at: null };
  next = { data: served, error: null, isError: false };
});

describe("student session screen", () => {
  it("reads pre-teaching before the question it prepares for", () => {
    render(<StudentSessionScreen trainingSessionId={5} />);

    const preteach = screen.getByRole("region", { name: "Before you start" });
    expect(precedes(preteach, screen.getByText("Question 1"))).toBe(true);
    expect(screen.getByText("Pre-teaching text")).toBeInTheDocument();
  });

  it("reads the verdict before the tutorial it unlocked", async () => {
    render(<StudentSessionScreen trainingSessionId={5} />);

    await userEvent.type(screen.getByRole("textbox"), "6");
    await userEvent.click(screen.getByRole("button", { name: /Submit answer/ }));

    const tutorial = await screen.findByRole("region", { name: "Work through it" });
    expect(precedes(screen.getByRole("button", { name: /Next question/ }), tutorial)).toBe(true);
    expect(screen.queryByRole("region", { name: "Before you start" })).not.toBeInTheDocument();
  });

  it("does not offer the answered question again while the next one loads", async () => {
    render(<StudentSessionScreen trainingSessionId={5} />);
    await userEvent.type(screen.getByRole("textbox"), "6");
    await userEvent.click(screen.getByRole("button", { name: /Submit answer/ }));

    // /next still holds attempt 11 until it returns.
    await userEvent.click(await screen.findByRole("button", { name: /Next question/ }));

    expect(screen.queryByText("Question 1")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Submit answer/ })).not.toBeInTheDocument();
  });

  it("drops the answered question while the next one is being written", () => {
    // A failed fetch keeps the last good `data`: the question just answered.
    next = {
      data: served,
      error: new ApiError(409, "question_generating", "A new question is being written"),
      isError: true,
    };
    render(<StudentSessionScreen trainingSessionId={5} />);

    expect(screen.getByText("A new question is being written")).toBeInTheDocument();
    expect(screen.queryByText("Question 1")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Submit answer/ })).not.toBeInTheDocument();
    expect(screen.queryByText("Pre-teaching text")).not.toBeInTheDocument();
  });

  it("keeps the result up with a progress bar while the next question is written", async () => {
    const view = render(<StudentSessionScreen trainingSessionId={5} />);
    await userEvent.type(screen.getByRole("textbox"), "6");
    await userEvent.click(screen.getByRole("button", { name: /Submit answer/ }));

    next = {
      data: served,
      error: new ApiError(409, "question_generating", "A new question is being written"),
      isError: true,
    };
    await userEvent.click(await screen.findByRole("button", { name: /Next question/ }));
    view.rerender(<StudentSessionScreen trainingSessionId={5} />);

    expect(screen.getByRole("status")).toHaveTextContent("A new question is being written");
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
    expect(screen.getByText("Worked tutorial text")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Preparing next question/ })).toBeDisabled();

    next = { data: { ...served, attempt_id: 12, ordinal: 2 }, error: null, isError: false };
    view.rerender(<StudentSessionScreen trainingSessionId={5} />);

    expect(await screen.findByText("Question 2")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.queryByText("Worked tutorial text")).not.toBeInTheDocument();
  });

  it("offers neither question nor tutorial once the run has ended", () => {
    session = { ended_at: "2026-10-24T11:00:00" };
    render(<StudentSessionScreen trainingSessionId={5} />);

    expect(screen.getByText("Session closed")).toBeInTheDocument();
    expect(screen.queryByText("Question 1")).not.toBeInTheDocument();
    expect(screen.queryByText("Pre-teaching text")).not.toBeInTheDocument();
  });
});
