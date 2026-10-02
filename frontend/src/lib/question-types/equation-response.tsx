"use client";

import {
  CodeBlock,
  MissingField,
  ReviewChip,
  statusTone,
} from "@/app/courses/[courseId]/review/components/review-primitives";
import {
  checkByName,
  presentStringArray,
  presentText,
} from "@/app/courses/[courseId]/review/review-utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type {
  AnswerInputProps,
  AuthoringReviewProps,
  QuestionContent,
  QuestionTypeUI,
  ReviewContentProps,
} from "./registry";
import { ExplanationPanel } from "./review-panels";

const ANSWER_LABEL = "Your answer";

/** Shown when the served question carries no hint of its own. */
const FALLBACK_HINT = "Use ^ for powers (x^2) and * for multiplication; 2x also means 2*x.";

function answerKey(content: QuestionContent) {
  return {
    expected: presentText(content.expected),
    variables: presentStringArray(content.variables) ?? [],
    equation: content.equation === true,
    functions: presentStringArray(content.allowed_functions),
  };
}

// One line of plain math text. The hint (syntax and the allowed variable names) comes from the
// backend, so it never carries the expected answer.
function EquationAnswerInput({ question, value, onChange, onSubmit }: AnswerInputProps) {
  const inputId = `answer-${question.attempt_id}`;
  const hintId = `${inputId}-hint`;
  return (
    <div className="space-y-2">
      <label className="font-medium text-foreground text-sm" htmlFor={inputId}>
        {ANSWER_LABEL}
      </label>
      <Input
        id={inputId}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            onSubmit?.();
          }
        }}
        aria-describedby={hintId}
        autoComplete="off"
        autoCapitalize="off"
        autoCorrect="off"
        spellCheck={false}
        maxLength={300}
        className="h-12 rounded-[1.2rem] border-border/80 bg-card/85 px-4 font-mono text-base md:text-sm"
        placeholder="Type your answer"
      />
      <p id={hintId} className="text-muted-foreground text-xs leading-5">
        {question.answer_hint ?? FALLBACK_HINT} Press Enter to submit.
      </p>
    </div>
  );
}

// The expected answer beside what the student typed. Equivalent forms all score, so the expected
// one is labelled "one correct answer" rather than "the answer".
function EquationReview({ content, submittedAnswer }: ReviewContentProps) {
  const { expected, variables } = answerKey(content);
  if (expected === null) return null;
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <div className="font-medium text-[11px] text-muted-foreground uppercase tracking-[0.14em]">
            One correct answer
          </div>
          <pre className="overflow-x-auto whitespace-pre-wrap rounded-lg border border-border/70 bg-muted/20 p-3 font-mono text-foreground text-sm leading-6">
            {expected}
          </pre>
        </div>
        {submittedAnswer !== undefined ? (
          <div className="space-y-1">
            <div className="font-medium text-[11px] text-muted-foreground uppercase tracking-[0.14em]">
              Your answer
            </div>
            <pre className="overflow-x-auto whitespace-pre-wrap rounded-lg border border-border/70 bg-muted/20 p-3 font-mono text-foreground text-sm leading-6">
              {submittedAnswer.trim() === "" ? "(nothing submitted)" : submittedAnswer}
            </pre>
          </div>
        ) : null}
      </div>
      <p className="text-muted-foreground text-xs">
        Any equivalent form
        {variables.length > 0 ? (
          <>
            {" in "}
            <span className="font-mono">{variables.join(", ")}</span>
          </>
        ) : null}{" "}
        is marked correct.
      </p>
    </div>
  );
}

function EquationAuthoringReview({ detail }: AuthoringReviewProps) {
  const checks = detail.validation_checks;
  const { expected, variables, equation, functions } = answerKey(detail.content ?? {});
  const notInPrompt = checkByName(checks, "equation_answer_not_in_prompt");
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_20rem]">
      <Card className="review-panel border">
        <CardHeader>
          <CardTitle>Expected answer</CardTitle>
          <CardDescription>
            {equation
              ? "An equation; any nonzero multiple of it is marked correct."
              : "An expression; any equivalent form is marked correct."}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {expected ? (
            <CodeBlock>{expected}</CodeBlock>
          ) : (
            <MissingField label="Expected answer is missing." />
          )}
          {notInPrompt ? (
            <ReviewChip tone={statusTone(notInPrompt.passed)}>
              {notInPrompt.passed ? "not stated in the prompt" : "stated in the prompt"}
            </ReviewChip>
          ) : null}
        </CardContent>
      </Card>
      <div className="space-y-4">
        <Card className="review-panel border">
          <CardHeader>
            <CardTitle>Variables</CardTitle>
            <CardDescription>The only symbols a student's answer may use.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {variables.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {variables.map((name) => (
                  <ReviewChip key={name} tone="accent" className="font-mono">
                    {name}
                  </ReviewChip>
                ))}
              </div>
            ) : (
              <MissingField label="No variables: the answer is a number." />
            )}
            <p className="text-[var(--review-muted)] text-xs">
              {functions === null
                ? "All supported functions are allowed."
                : functions.length > 0
                  ? `Functions allowed: ${functions.join(", ")}.`
                  : "No functions are allowed."}
            </p>
          </CardContent>
        </Card>
        <ExplanationPanel detail={detail} />
      </div>
    </div>
  );
}

export const equationResponse: QuestionTypeUI = {
  kind: "discrete",
  label: "Equation response",
  shortLabel: "Equation",
  answerLabel: ANSWER_LABEL,
  AnswerInput: EquationAnswerInput,
  ReviewContent: EquationReview,
  AuthoringReview: EquationAuthoringReview,
};
