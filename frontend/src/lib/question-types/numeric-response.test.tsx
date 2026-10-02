import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { QuestionDetail } from "@/lib/api/types";
import {
  formatQuantity,
  formatTolerance,
  joinAnswer,
  numericResponse,
  splitAnswer,
} from "./numeric-response";
import type { AuthoringReviewProps, QuestionContent, StudentQuestion } from "./registry";

const CONTENT: QuestionContent = {
  prompt: "A ball is dropped from rest. Its acceleration?",
  value: 9.81,
  unit: "m/s^2",
  relative_tolerance: 0.01,
  absolute_tolerance: null,
  accepted_units: null,
  sig_figs: null,
  explanation: "Every falling body accelerates at g.",
};

function served(
  hint: string | null = "Give a number with its unit, e.g. in m/s^2.",
): StudentQuestion {
  return {
    attempt_id: 7,
    question_type: "numeric_response",
    prompt: CONTENT.prompt,
    answer_hint: hint,
  } as unknown as StudentQuestion;
}

function authoringProps(content: QuestionContent, checks: unknown[] = []): AuthoringReviewProps {
  const detail = {
    question: { id: 3, question_type: "numeric_response", prompt: "p", difficulty: "easy" },
    content,
    validation_checks: checks,
  } as unknown as QuestionDetail;
  return {
    detail,
    isInlineEditing: false,
    promptEdit: "p",
    referenceEdit: "9.81 m/s^2",
    testsEdit: "",
    onPromptEdit: () => {},
    onReferenceEdit: () => {},
    onTestsEdit: () => {},
  };
}

function ui() {
  if (!numericResponse) throw new Error("numeric_response has no UI");
  return numericResponse;
}

describe("numeric response answer string", () => {
  it("splits at the first space and joins back to the grader's form", () => {
    expect(splitAnswer("9.81 m/s^2")).toEqual({ number: "9.81", unit: "m/s^2" });
    expect(splitAnswer("9.81")).toEqual({ number: "9.81", unit: "" });
    expect(splitAnswer("")).toEqual({ number: "", unit: "" });
    expect(splitAnswer("1 kg m/s")).toEqual({ number: "1", unit: "kg m/s" });
    expect(joinAnswer("9.81", "m/s^2")).toBe("9.81 m/s^2");
    expect(joinAnswer("9.81", "")).toBe("9.81");
    for (const value of ["9.81 m/s^2", "75", " m", "1 kg m/s"]) {
      const { number, unit } = splitAnswer(value);
      expect(joinAnswer(number, unit)).toBe(value);
    }
  });
});

describe("numeric response answer input", () => {
  it("combines the number and unit fields into one answer", () => {
    const onChange = vi.fn();
    const { AnswerInput } = ui();
    const { rerender } = render(<AnswerInput question={served()} value="" onChange={onChange} />);

    fireEvent.change(screen.getByLabelText("Number"), { target: { value: "9.81" } });
    expect(onChange).toHaveBeenLastCalledWith("9.81");

    rerender(<AnswerInput question={served()} value="9.81" onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("Unit"), { target: { value: "m/s^2" } });
    expect(onChange).toHaveBeenLastCalledWith("9.81 m/s^2");

    rerender(<AnswerInput question={served()} value="9.81 m/s^2" onChange={onChange} />);
    expect(screen.getByLabelText("Number")).toHaveProperty("value", "9.81");
    expect(screen.getByLabelText("Unit")).toHaveProperty("value", "m/s^2");
    // A space typed into the number would move text into the unit; it is dropped instead.
    fireEvent.change(screen.getByLabelText("Number"), { target: { value: "9. 8" } });
    expect(onChange).toHaveBeenLastCalledWith("9.8 m/s^2");
  });

  it("shows the served hint and submits on Enter only with a number", () => {
    const onSubmit = vi.fn();
    const { AnswerInput } = ui();
    const { rerender } = render(
      <AnswerInput question={served()} value="" onChange={() => {}} onSubmit={onSubmit} />,
    );
    expect(screen.getByText(/Give a number with its unit, e\.g\. in m\/s\^2\./)).toBeTruthy();

    fireEvent.keyDown(screen.getByLabelText("Unit"), { key: "Enter" });
    expect(onSubmit).not.toHaveBeenCalled();

    rerender(
      <AnswerInput
        question={served()}
        value="9.81 m/s^2"
        onChange={() => {}}
        onSubmit={onSubmit}
      />,
    );
    fireEvent.keyDown(screen.getByLabelText("Unit"), { key: "Enter" });
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });
});

describe("numeric response reviews", () => {
  it("formats the key and its tolerance", () => {
    expect(formatQuantity(CONTENT)).toBe("9.81 m/s^2");
    expect(formatQuantity({ ...CONTENT, unit: "" })).toBe("9.81");
    expect(formatQuantity({ unit: "m" })).toBeNull();
    expect(formatTolerance(CONTENT)).toBe("within 1%");
    expect(formatTolerance({ ...CONTENT, relative_tolerance: null, absolute_tolerance: 0.5 })).toBe(
      "within ±0.5 m/s^2",
    );
    expect(formatTolerance({ ...CONTENT, absolute_tolerance: 0.5 })).toBe(
      "within 1% or ±0.5 m/s^2",
    );
    expect(formatTolerance({ ...CONTENT, relative_tolerance: 0.025 })).toBe("within 2.5%");
    expect(formatTolerance({})).toBeNull();
  });

  it("shows the student the correct value, unit and tolerance", () => {
    const { ReviewContent } = ui();
    render(<ReviewContent content={CONTENT} submittedAnswer="981 cm/s^2" />);
    expect(screen.getByText("Correct answer: 9.81 m/s^2")).toBeTruthy();
    expect(screen.getByText("Your answer: 981 cm/s^2")).toBeTruthy();
    expect(screen.getByText("Accepted within 1%.")).toBeTruthy();
  });

  it("renders nothing for a stored key without a value", () => {
    const { ReviewContent } = ui();
    const { container } = render(<ReviewContent content={{ unit: "m" }} />);
    expect(container.firstChild).toBeNull();
  });

  it("shows the instructor value, unit, tolerance, accepted units and explanation", () => {
    const { AuthoringReview } = ui();
    render(
      <AuthoringReview
        {...authoringProps({ ...CONTENT, accepted_units: ["m/s^2", "cm/s^2"], sig_figs: 3 }, [
          {
            name: "numeric_value_not_in_prompt",
            passed: true,
            deterministic: true,
            severity: "error",
            detail: "The prompt does not state the answer",
            evidence: null,
          },
        ])}
      />,
    );
    expect(screen.getByText("9.81")).toBeTruthy();
    expect(screen.getByText("m/s^2")).toBeTruthy();
    expect(screen.getByText("within 1%")).toBeTruthy();
    expect(screen.getByText("m/s^2, cm/s^2")).toBeTruthy();
    expect(screen.getByText("at least 3")).toBeTruthy();
    expect(screen.getByText("answer not stated")).toBeTruthy();
    expect(screen.getByText("Every falling body accelerates at g.")).toBeTruthy();
  });

  it("is a discrete type with its own labels", () => {
    expect(ui().label).toBe("Numeric response");
    expect(ui().shortLabel).toBe("Numeric");
    expect(ui().kind).toBe("discrete");
    expect(ui().answerLabel).toBe("Your answer");
  });
});
