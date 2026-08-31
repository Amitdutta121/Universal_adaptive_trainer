/** "What was correct" — the answer key, read back after a question is scored. */

import { Check, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { parseParsonsAnswer, type Question } from "../mock-data";

function MultipleChoiceReview({ question, answer }: { question: Question; answer: string }) {
  const chosenIndex = answer.trim() === "" ? null : Number.parseInt(answer, 10);
  return (
    <ul className="space-y-2">
      {(question.options ?? []).map((option, index) => {
        const isCorrect = index === question.correctOptionIndex;
        const isWrongPick = chosenIndex === index && !isCorrect;
        return (
          <li
            key={option}
            className={cn(
              "flex items-start justify-between gap-3 rounded-lg border px-3 py-2 text-sm",
              isCorrect && "border-primary/40 bg-primary/5",
              isWrongPick && "border-destructive/40 bg-destructive/10",
              !isCorrect && !isWrongPick && "border-border bg-muted/30",
            )}
          >
            <span className="text-foreground">
              <span className="mr-2 font-mono text-muted-foreground text-xs">
                {String.fromCharCode(65 + index)}
              </span>
              {option}
            </span>
            {isCorrect ? (
              <span className="flex shrink-0 items-center gap-1 font-medium text-primary text-xs">
                <Check className="size-3.5" aria-hidden="true" />
                Correct answer
              </span>
            ) : null}
            {isWrongPick ? (
              <span className="flex shrink-0 items-center gap-1 font-medium text-destructive text-xs">
                <X className="size-3.5" aria-hidden="true" />
                Your answer
              </span>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

function TrueFalseReview({ question, answer }: { question: Question; answer: string }) {
  const correctLabel = question.correctBoolean ? "True" : "False";
  const chosen = answer.trim().toLowerCase();
  const chosenLabel = chosen === "true" ? "True" : chosen === "false" ? "False" : null;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Badge variant="secondary">Correct answer: {correctLabel}</Badge>
      {chosenLabel && chosenLabel !== correctLabel ? (
        <Badge variant="destructive">Your answer: {chosenLabel}</Badge>
      ) : null}
    </div>
  );
}

function TextReview({ question, answer }: { question: Question; answer: string }) {
  const expected = question.acceptableAnswers?.[0] ?? "";
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <div className="space-y-1">
        <div className="font-medium text-muted-foreground text-xs uppercase tracking-wide">
          Expected
        </div>
        <pre className="overflow-x-auto whitespace-pre-wrap rounded-lg border border-primary/30 bg-primary/5 p-3 font-mono text-foreground text-xs leading-6">
          {expected}
        </pre>
      </div>
      <div className="space-y-1">
        <div className="font-medium text-muted-foreground text-xs uppercase tracking-wide">
          Your answer
        </div>
        <pre className="overflow-x-auto whitespace-pre-wrap rounded-lg border border-border bg-muted/40 p-3 font-mono text-foreground text-xs leading-6">
          {answer.trim() === "" ? "(nothing submitted)" : answer}
        </pre>
      </div>
    </div>
  );
}

function ParsonsReview({ question, answer }: { question: Question; answer: string }) {
  const correctText = (question.steps ?? []).map((step) => step.text).join("\n");
  const submittedIds = parseParsonsAnswer(answer);
  const stepById = new Map((question.steps ?? []).map((step) => [step.id, step]));
  const yourText = submittedIds.map((id) => stepById.get(id)?.text ?? id).join("\n");
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <div className="space-y-1">
        <div className="font-medium text-muted-foreground text-xs uppercase tracking-wide">
          Correct order
        </div>
        <pre className="overflow-x-auto whitespace-pre rounded-lg border border-primary/30 bg-primary/5 p-3 font-mono text-foreground text-xs leading-6">
          {correctText}
        </pre>
      </div>
      <div className="space-y-1">
        <div className="font-medium text-muted-foreground text-xs uppercase tracking-wide">
          Your order
        </div>
        <pre className="overflow-x-auto whitespace-pre rounded-lg border border-border bg-muted/40 p-3 font-mono text-foreground text-xs leading-6">
          {yourText || "(nothing submitted)"}
        </pre>
      </div>
    </div>
  );
}

export function AnswerReview({ question, answer }: { question: Question; answer: string }) {
  return (
    <div className="space-y-3">
      {question.type === "multiple_choice" ? (
        <MultipleChoiceReview question={question} answer={answer} />
      ) : null}
      {question.type === "true_false" ? (
        <TrueFalseReview question={question} answer={answer} />
      ) : null}
      {question.type === "short_text" || question.type === "output_prediction" ? (
        <TextReview question={question} answer={answer} />
      ) : null}
      {question.type === "parsons" ? <ParsonsReview question={question} answer={answer} /> : null}
      <p className="text-muted-foreground text-sm leading-6">{question.explanation}</p>
    </div>
  );
}
