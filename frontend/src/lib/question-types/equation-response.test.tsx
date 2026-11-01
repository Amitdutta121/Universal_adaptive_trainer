import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { QuestionDetail } from "@/lib/api/types";
import { equationResponse } from "./equation-response";
import type { AuthoringReviewProps, QuestionContent, StudentQuestion } from "./registry";

const HINT = "Write an expression using m and v. Use ^ for powers (x^2) and * for multiplication.";

const CONTENT: QuestionContent = {
  prompt: "Write the kinetic energy of a mass m moving at speed v.",
  expected: "m*v^2/2",
  variables: ["m", "v"],
  equation: false,
  explanation: "Kinetic energy is one half m v squared.",
};

function served(answerHint: string | null): StudentQuestion {
  return {
    attempt_id: 9,
    question_type: "equation_response",
    prompt: CONTENT.prompt,
    answer_hint: answerHint,
  } as unknown as StudentQuestion;
}

function authoringProps(content: QuestionContent, passed: boolean): AuthoringReviewProps {
  const detail = {
    question: { id: 4, question_type: "equation_response", prompt: "p", difficulty: "easy" },
    content,
    validation_checks: [
      { name: "equation_answer_not_in_prompt", passed, detail: "Prompt does not state the answer" },
    ],
  } as unknown as QuestionDetail;
  return {
    detail,
    isInlineEditing: false,
    promptEdit: "p",
    referenceEdit: "",
    testsEdit: "",
    onPromptEdit: () => {},
    onReferenceEdit: () => {},
    onTestsEdit: () => {},
  };
}

describe("equationResponse", () => {
  it("is a built discrete type", () => {
    expect(equationResponse.label).toBe("Equation response");
    expect(equationResponse.shortLabel).toBe("Equation");
    expect(equationResponse.kind).toBe("discrete");
    expect(equationResponse.hasTests).toBeUndefined();
  });

  it("takes one line of math text, shows the served hint and submits on Enter", () => {
    const onChange = vi.fn();
    const onSubmit = vi.fn();
    const { AnswerInput } = equationResponse;
    render(
      <AnswerInput question={served(HINT)} value="" onChange={onChange} onSubmit={onSubmit} />,
    );

    const input = screen.getByLabelText("Your answer");
    expect(input.tagName).toBe("INPUT");
    expect(input).toHaveAccessibleDescription(`${HINT} Press Enter to submit.`);

    fireEvent.change(input, { target: { value: "m v^2 / 2" } });
    expect(onChange).toHaveBeenCalledWith("m v^2 / 2");
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it("falls back to the syntax help when the question has no hint", () => {
    const { AnswerInput } = equationResponse;
    render(<AnswerInput question={served(null)} value="" onChange={() => {}} />);
    expect(screen.getByText(/Use \^ for powers/)).toBeInTheDocument();
  });

  it("shows the student one correct answer, their answer and the variables", () => {
    const { ReviewContent } = equationResponse;
    render(<ReviewContent content={CONTENT} submittedAnswer="m*v^2" />);
    expect(screen.getByText("m*v^2/2")).toBeInTheDocument();
    expect(screen.getByText("m*v^2")).toBeInTheDocument();
    expect(screen.getByText("m, v")).toBeInTheDocument();
  });

  it("renders nothing for content with no expected answer", () => {
    const { ReviewContent } = equationResponse;
    const { container } = render(<ReviewContent content={{}} />);
    expect(container.firstChild).toBeNull();
  });

  it("gives the instructor the key, the variables, the explanation and the leak check", () => {
    const { AuthoringReview } = equationResponse;
    render(<AuthoringReview {...authoringProps(CONTENT, true)} />);
    expect(screen.getByText("m*v^2/2")).toBeInTheDocument();
    expect(screen.getByText("m")).toBeInTheDocument();
    expect(screen.getByText("v")).toBeInTheDocument();
    expect(screen.getByText(CONTENT.explanation as string)).toBeInTheDocument();
    expect(screen.getByText("not stated in the prompt")).toBeInTheDocument();
    expect(screen.getByText("All supported functions are allowed.")).toBeInTheDocument();
  });

  it("flags a prompt that states the answer, and restricted functions", () => {
    const { AuthoringReview } = equationResponse;
    render(
      <AuthoringReview
        {...authoringProps(
          { ...CONTENT, expected: "y = 2*x", equation: true, allowed_functions: ["sin"] },
          false,
        )}
      />,
    );
    expect(screen.getByText("stated in the prompt")).toBeInTheDocument();
    expect(screen.getByText(/nonzero multiple/)).toBeInTheDocument();
    expect(screen.getByText("Functions allowed: sin.")).toBeInTheDocument();
  });
});
