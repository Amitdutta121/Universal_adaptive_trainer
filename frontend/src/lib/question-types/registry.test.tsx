import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { QuestionDetail } from "@/lib/api/types";
import { equationResponse } from "./equation-response";
import { numericResponse } from "./numeric-response";
import {
  type AuthoringReviewProps,
  BUILT_QUESTION_TYPES,
  QUESTION_TYPE_UI,
  type QuestionContent,
  type QuestionTypeUI,
  type StudentQuestion,
} from "./registry";

const SEVEN = [
  "multiple_choice",
  "true_false",
  "output_prediction",
  "code_completion",
  "debugging",
  "parsons",
  "coding",
] as const;

const BLOCKS = [
  { id: "b1", text: "def f():", indent: 0 },
  { id: "b2", text: "return 1", indent: 1 },
];

// Minimal served question per type: only the fields its AnswerInput reads.
function served(type: (typeof SEVEN)[number]): StudentQuestion {
  return {
    attempt_id: 7,
    question_type: type,
    options: type === "multiple_choice" ? ["first", "second"] : null,
    blocks: type === "parsons" ? BLOCKS : null,
  } as unknown as StudentQuestion;
}

// Minimal answer-key content per type: only the fields its review reads.
const CONTENT: Record<(typeof SEVEN)[number], QuestionContent> = {
  multiple_choice: { options: ["first", "second"], correct_option_index: 1 },
  true_false: { correct_answer: true },
  output_prediction: { code: "print(1)", expected_output: "1" },
  code_completion: { code: "def f():\n    pass" },
  debugging: { code: "def f(:" },
  parsons: { blocks: BLOCKS, correct_order: ["b1", "b2"] },
  coding: {},
};

function authoringProps(type: (typeof SEVEN)[number]): AuthoringReviewProps {
  const detail = {
    question: { id: 3, question_type: type, prompt: "Do it", difficulty: "easy" },
    content: CONTENT[type],
    validation_checks: [],
  } as unknown as QuestionDetail;
  return {
    detail,
    isInlineEditing: false,
    promptEdit: "Do it",
    referenceEdit: "def f():\n    return 1",
    testsEdit: "",
    onPromptEdit: () => {},
    onReferenceEdit: () => {},
    onTestsEdit: () => {},
  };
}

function built(type: (typeof SEVEN)[number]): QuestionTypeUI {
  const ui = QUESTION_TYPE_UI[type];
  if (!ui) throw new Error(`${type} has no UI`);
  return ui;
}

describe("QUESTION_TYPE_UI", () => {
  it("builds the seven existing types, in canonical order", () => {
    expect(BUILT_QUESTION_TYPES).toEqual(SEVEN);
  });

  it("keeps numeric and equation response as unbuilt placeholders", () => {
    expect(numericResponse).toBeNull();
    expect(equationResponse).toBeNull();
    expect(QUESTION_TYPE_UI.numeric_response).toBeNull();
    expect(QUESTION_TYPE_UI.equation_response).toBeNull();
  });

  it.each(SEVEN)("%s renders its answer input", (type) => {
    const { AnswerInput } = built(type);
    const { container } = render(
      <AnswerInput question={served(type)} value="" onChange={() => {}} />,
    );
    expect(container.firstChild).not.toBeNull();
  });

  it.each(["multiple_choice", "true_false", "output_prediction", "parsons"] as const)(
    "%s renders its student review",
    (type) => {
      const { ReviewContent } = built(type);
      const { container } = render(<ReviewContent content={CONTENT[type]} submittedAnswer="0" />);
      expect(container.firstChild).not.toBeNull();
    },
  );

  it.each(["code_completion", "debugging", "coding"] as const)(
    "%s leaves the student review to the reference solution block",
    (type) => {
      const { ReviewContent, showReferenceSolution } = built(type);
      const { container } = render(<ReviewContent content={CONTENT[type]} />);
      expect(container.firstChild).toBeNull();
      expect(showReferenceSolution).toBe(true);
    },
  );

  it.each(SEVEN)("%s renders its instructor review", (type) => {
    const { AuthoringReview } = built(type);
    const { container } = render(<AuthoringReview {...authoringProps(type)} />);
    expect(container.firstChild).not.toBeNull();
  });

  it("keeps the shipped answer labels", () => {
    expect(built("output_prediction").answerLabel).toBe("Your answer");
    expect(built("coding").answerLabel).toBe("Your Python");
  });
});
