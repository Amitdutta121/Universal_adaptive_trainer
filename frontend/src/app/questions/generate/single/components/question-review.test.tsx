import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

// The child review components render deep trees that need a full QuestionDetail;
// this test is about QuestionReview's own wiring (optional onGenerateAnother, the
// regenerate box), so they are stubbed to nothing.
vi.mock("@/app/review/components/review-question-content", () => ({
  ReviewQuestionSurface: () => null,
  ReviewQuestionContent: () => null,
}));
vi.mock("@/app/review/components/review-feedback", () => ({
  JudgeRail: () => null,
  ValidationSummary: () => null,
}));
vi.mock("@/app/review/use-review-form", () => ({
  useReviewForm: () => ({
    decision: "approve",
    effectiveDecision: "approve",
    reasons: [],
    changedFields: [],
    comment: "",
    isInlineEditing: false,
    promptEdit: "",
    referenceEdit: "",
    testsEdit: "",
    setDecision: vi.fn(),
    setReasons: vi.fn(),
    setComment: vi.fn(),
    setPromptEdit: vi.fn(),
    setReferenceEdit: vi.fn(),
    setTestsEdit: vi.fn(),
  }),
}));

const regenerateMutateAsync = vi.fn();
const useRegenerateWithFeedback = vi.fn(() => ({
  mutateAsync: regenerateMutateAsync,
  isPending: false,
  isError: false,
  error: null,
}));

vi.mock("@/lib/api/queries", () => ({
  useQuestion: () => ({
    data: {
      question: { id: 1, prompt: "p", question_type: "multiple_choice", difficulty: "easy" },
      reference_solution: null,
      tests: null,
      taxonomy: { topic: "T", subtopics: [] },
      validation_checks: [],
    },
    isPending: false,
    isError: false,
    error: null,
  }),
  useSubmitReview: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRegenerateWithFeedback: () => useRegenerateWithFeedback(),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { QuestionReview } from "./question-review";

describe("QuestionReview", () => {
  it("hides Skip when onGenerateAnother is not given", () => {
    render(<QuestionReview questionId={1} />);
    expect(screen.queryByRole("button", { name: "Skip" })).not.toBeInTheDocument();
  });

  it("shows Skip when onGenerateAnother is given", () => {
    render(<QuestionReview questionId={1} onGenerateAnother={vi.fn()} />);
    expect(screen.getByRole("button", { name: /skip/i })).toBeInTheDocument();
  });

  it("keeps the regenerate button disabled until feedback is typed, then reports the new id", async () => {
    const user = userEvent.setup();
    regenerateMutateAsync.mockResolvedValueOnce({ question_id: 42 });
    const onRegenerated = vi.fn();

    render(<QuestionReview questionId={1} onRegenerated={onRegenerated} />);

    const button = screen.getByRole("button", { name: /regenerate with feedback/i });
    expect(button).toBeDisabled();

    await user.type(
      screen.getByPlaceholderText(/plausible misconceptions/i),
      "make the distractors subtler",
    );
    expect(button).toBeEnabled();

    await user.click(button);
    expect(regenerateMutateAsync).toHaveBeenCalledWith({
      questionId: 1,
      feedback: "make the distractors subtler",
    });
    expect(onRegenerated).toHaveBeenCalledWith(42);
  });
});
